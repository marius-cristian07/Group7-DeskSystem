"""PostgreSQL storage for S6-3: unresolved failures, resolution and acknowledgement.

One advisory lock keeps four things from racing past each other:

* the scheduler claiming a new cleaning start (exclusive),
* a manager resolving a run, operation or incident (exclusive),
* a group operation being created or changed in the database (shared, see
  group_operation_repository.save_operation).

Exclusive holders wait for each other and for every shared holder. So a resolution
cannot commit while an operation for the same desks is being created, and a start
claim never reads a half-finished resolution. Hold it only for the short queries
inside a transaction. Never wait for the simulator or the service while holding it.
"""

import logging
import os

from psycopg2.extras import Json

from .database import transaction

logger = logging.getLogger(__name__)

# 52002 is the key S5-2 already uses for schedule edits; the second number is a different lock.
REVIEW_LOCK = (52002, 2)

SUBJECT_RUN = "cleaning_run"
SUBJECT_OPERATION = "group_operation"
SUBJECT_INCIDENT = "desk_incident"

# Runs that are still moving or waiting for review. Another automatic start must not touch their desks.
_RUN_STATES_THAT_BLOCK_STARTS = ("needs_review", "raising", "cleaning", "returning")
# Group operations that have not finished.
_ACTIVE_OPERATION_STATES = ("pending_warning", "countdown", "dispatching", "monitoring")


def block_on_every_unresolved_incident():
    """Strict mode (CLEANING_BLOCK_ON_ALL_UNRESOLVED_INCIDENTS=1).

    By default an incident blocks automatic starts while its fault is active, and afterwards
    while it is unresolved IF it happened during a group operation (it is linked to one). A
    fault that came and went by itself with no movement involved stays listed for review
    but does not stop cleaning. Strict mode makes every unresolved incident block."""
    return os.environ.get("CLEANING_BLOCK_ON_ALL_UNRESOLVED_INCIDENTS", "0").strip() == "1"


def incident_blocks_starts(is_active, operation_id, strict=None):
    strict = block_on_every_unresolved_incident() if strict is None else strict
    return bool(is_active or operation_id is not None or strict)


class ReviewError(Exception):
    """A review request could not be carried out. `reason` selects the HTTP status."""

    def __init__(self, message, reason):
        super().__init__(message)
        self.reason = reason


def lock_review_state(cursor, shared=False):
    """Take the review lock until the surrounding transaction ends."""
    function = "pg_advisory_xact_lock_shared" if shared else "pg_advisory_xact_lock"
    cursor.execute(f"SELECT {function}(%s, %s)", REVIEW_LOCK)


# ---------- which desks a record involves ----------

def _run_desk_ids(cursor, run_id):
    """Desks of the schedule plus desks of both of its operations, so edits cannot hide any."""
    cursor.execute(
        """
        SELECT sd.desk_id
        FROM cleaning_runs AS r
        JOIN cleaning_schedule_desks AS sd ON sd.schedule_id = r.schedule_id
        WHERE r.run_id = %s
        UNION
        SELECT od.desk_id
        FROM cleaning_runs AS r
        JOIN group_operation_desks AS od
          ON od.operation_id IN (r.raise_operation_id, r.return_operation_id)
        WHERE r.run_id = %s
        """,
        (run_id, run_id),
    )
    return sorted(row[0] for row in cursor.fetchall())


def _operation_desk_ids(cursor, operation_id):
    cursor.execute(
        "SELECT desk_id FROM group_operation_desks WHERE operation_id = %s ORDER BY desk_id",
        (operation_id,),
    )
    return [row[0] for row in cursor.fetchall()]


# ---------- blockers for an automatic cleaning start ----------

def find_start_blockers(cursor, desk_ids):
    """Everything that makes an automatic movement of these desks unsafe right now.

    It looks at every schedule and every operation, not only at the one that is asking:
    two schedules that share a desk share its unresolved problems. The caller holds the
    exclusive review lock, so the answer cannot change under it through a resolution.
    """
    blockers = []

    cursor.execute(
        """
        SELECT DISTINCT r.run_id, r.status, r.schedule_id
        FROM cleaning_runs AS r
        LEFT JOIN cleaning_schedule_desks AS sd ON sd.schedule_id = r.schedule_id
        LEFT JOIN group_operation_desks AS od
          ON od.operation_id IN (r.raise_operation_id, r.return_operation_id)
        WHERE r.status = ANY(%s)
          AND (sd.desk_id = ANY(%s) OR od.desk_id = ANY(%s))
        ORDER BY r.run_id
        """,
        (list(_RUN_STATES_THAT_BLOCK_STARTS), desk_ids, desk_ids),
    )
    for run_id, status, schedule_id in cursor.fetchall():
        blockers.append({
            "type": SUBJECT_RUN, "id": str(run_id), "status": status, "schedule_id": schedule_id,
        })

    cursor.execute(
        """
        SELECT o.operation_id, o.state, o.review_state, array_agg(d.desk_id ORDER BY d.desk_id)
        FROM group_operations AS o
        JOIN group_operation_desks AS d ON d.operation_id = o.operation_id
        WHERE d.desk_id = ANY(%s)
          AND (o.review_state = 'needs_review' OR o.state = ANY(%s))
        GROUP BY o.operation_id, o.state, o.review_state, o.created_at
        ORDER BY o.created_at, o.operation_id
        """,
        (desk_ids, list(_ACTIVE_OPERATION_STATES)),
    )
    for operation_id, state, review_state, desks in cursor.fetchall():
        blockers.append({
            "type": SUBJECT_OPERATION, "id": operation_id, "status": state,
            "review_state": review_state, "desk_ids": desks,
        })

    cursor.execute(
        """
        SELECT incident_id, desk_id, fault_category, cleared_at IS NULL
        FROM desk_incidents
        WHERE desk_id = ANY(%s) AND review_state = 'needs_review'
          AND (cleared_at IS NULL OR operation_id IS NOT NULL OR %s)
        ORDER BY incident_id
        """,
        (desk_ids, block_on_every_unresolved_incident()),
    )
    for incident_id, desk_id, category, is_active in cursor.fetchall():
        blockers.append({
            "type": SUBJECT_INCIDENT, "id": str(incident_id), "status": "active" if is_active else "cleared",
            "fault_category": category, "desk_ids": [desk_id],
        })
    return blockers


def describe_blockers(blockers, limit=5):
    """One readable sentence for the run history, listing at most `limit` items."""
    names = {SUBJECT_RUN: "cleaning run", SUBJECT_OPERATION: "group operation", SUBJECT_INCIDENT: "desk incident"}
    parts = []
    for item in blockers[:limit]:
        label = f"{names[item['type']]} {item['id']} ({item.get('fault_category') or item['status']})"
        parts.append(label)
    if len(blockers) > limit:
        parts.append(f"{len(blockers) - limit} more")
    return (
        "Automatic start blocked by unresolved items on these desks: " + "; ".join(parts)
        + ". A manager must review and resolve them first. No desk was moved."
    )


# ---------- review context (read before the simulator is asked) ----------

def get_review_context(subject_type, subject_id):
    """What a resolution would need to check, or None if the subject does not exist."""
    with transaction() as cursor:
        if subject_type == SUBJECT_RUN:
            cursor.execute("SELECT status FROM cleaning_runs WHERE run_id = %s", (int(subject_id),))
            row = cursor.fetchone()
            if row is None:
                return None
            return {"reviewable": row[0] == "needs_review", "status": row[0],
                    "desk_ids": _run_desk_ids(cursor, int(subject_id))}
        if subject_type == SUBJECT_OPERATION:
            cursor.execute(
                "SELECT state, review_state FROM group_operations WHERE operation_id = %s", (subject_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return {"reviewable": row[1] == "needs_review", "status": row[1],
                    "desk_ids": _operation_desk_ids(cursor, subject_id)}
        cursor.execute(
            "SELECT review_state, cleared_at, desk_id FROM desk_incidents WHERE incident_id = %s",
            (int(subject_id),),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return {"reviewable": row[0] == "needs_review", "status": row[0],
                "active": row[1] is None, "desk_ids": [row[2]]}


# ---------- resolving ----------

def _require_idle(cursor, desk_ids, ignore_run_id=None):
    """No movement may be underway for these desks and none may report a current fault."""
    cursor.execute(
        """
        SELECT DISTINCT o.operation_id
        FROM group_operations AS o
        JOIN group_operation_desks AS d ON d.operation_id = o.operation_id
        WHERE d.desk_id = ANY(%s) AND o.state = ANY(%s)
        """,
        (desk_ids, list(_ACTIVE_OPERATION_STATES)),
    )
    busy = [row[0] for row in cursor.fetchall()]
    cursor.execute(
        """
        SELECT DISTINCT r.run_id
        FROM cleaning_runs AS r
        LEFT JOIN cleaning_schedule_desks AS sd ON sd.schedule_id = r.schedule_id
        LEFT JOIN group_operation_desks AS od
          ON od.operation_id IN (r.raise_operation_id, r.return_operation_id)
        WHERE r.status IN ('raising', 'returning')
          AND (%s::bigint IS NULL OR r.run_id <> %s::bigint)
          AND (sd.desk_id = ANY(%s) OR od.desk_id = ANY(%s))
        """,
        (ignore_run_id, ignore_run_id, desk_ids, desk_ids),
    )
    busy_runs = [row[0] for row in cursor.fetchall()]
    if busy or busy_runs:
        raise ReviewError(
            "A movement for these desks is still in progress. Wait until it has finished. Nothing was changed.",
            "busy",
        )
    cursor.execute(
        "SELECT desk_id FROM desk_incidents WHERE desk_id = ANY(%s) AND cleared_at IS NULL", (desk_ids,),
    )
    faulty = sorted({row[0] for row in cursor.fetchall()})
    if faulty:
        raise ReviewError(
            f"Desk(s) still have an active fault: {', '.join(faulty)}. Nothing was changed.", "desk_not_ready",
        )


def _add_record(cursor, subject_type, subject_id, action, decision, explanation, recorded_by, desk_checks):
    cursor.execute(
        """
        INSERT INTO review_records (
            subject_type, subject_id, action, decision, explanation, recorded_by, desk_checks
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING record_id, recorded_at
        """,
        (subject_type, str(subject_id), action, decision, explanation, recorded_by,
         None if desk_checks is None else Json(desk_checks)),
    )
    return cursor.fetchone()


def _resolve_linked(cursor, operation_ids, decision, explanation, recorded_by, desk_checks):
    """Resolve the operations still needing review and the cleared incidents they caused."""
    resolved = {"group_operations": [], "desk_incidents": []}
    if not operation_ids:
        return resolved
    cursor.execute(
        """
        UPDATE group_operations
        SET review_state = 'resolved', reviewed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
        WHERE operation_id = ANY(%s) AND review_state = 'needs_review'
        RETURNING operation_id
        """,
        (operation_ids,),
    )
    for (operation_id,) in cursor.fetchall():
        resolved["group_operations"].append(operation_id)
        _add_record(cursor, SUBJECT_OPERATION, operation_id, "resolved", decision, explanation,
                    recorded_by, desk_checks)
    cursor.execute(
        """
        UPDATE desk_incidents
        SET review_state = 'resolved', reviewed_at = CURRENT_TIMESTAMP
        WHERE operation_id = ANY(%s) AND review_state = 'needs_review' AND cleared_at IS NOT NULL
        RETURNING incident_id
        """,
        (operation_ids,),
    )
    for (incident_id,) in cursor.fetchall():
        resolved["desk_incidents"].append(incident_id)
        _add_record(cursor, SUBJECT_INCIDENT, incident_id, "resolved", decision, explanation,
                    recorded_by, desk_checks)
    return resolved


def _require_checked(desk_ids, desk_checks):
    unchecked = sorted(set(desk_ids) - set(desk_checks))
    if unchecked:
        raise ReviewError(
            f"The desks changed while this was being reviewed ({', '.join(unchecked)}). "
            "Try again. Nothing was changed.",
            "changed",
        )


def resolve_run(run_id, desk_checks, decision, explanation, recorded_by):
    """Mark a cleaning run, its operations and the incidents they caused as reviewed.

    This only writes review records. It sends no command to any desk."""
    with transaction() as cursor:
        lock_review_state(cursor)
        cursor.execute(
            """
            SELECT status, raise_operation_id, return_operation_id
            FROM cleaning_runs WHERE run_id = %s FOR UPDATE
            """,
            (run_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise ReviewError("Cleaning run not found", "not_found")
        status, raise_id, return_id = row
        if status != "needs_review":
            raise ReviewError(
                f"This run is not waiting for review (status: {status}). Nothing was changed.", "not_reviewable",
            )
        desk_ids = _run_desk_ids(cursor, run_id)
        _require_checked(desk_ids, desk_checks)
        _require_idle(cursor, desk_ids, ignore_run_id=run_id)

        cursor.execute(
            """
            UPDATE cleaning_runs
            SET status = 'resolved', reviewed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE run_id = %s AND status = 'needs_review'
            """,
            (run_id,),
        )
        record_id, recorded_at = _add_record(
            cursor, SUBJECT_RUN, run_id, "resolved", decision, explanation, recorded_by, desk_checks,
        )
        resolved = _resolve_linked(
            cursor, [item for item in (raise_id, return_id) if item], decision, explanation,
            recorded_by, desk_checks,
        )
    resolved["cleaning_runs"] = [run_id]
    return {"record_id": record_id, "recorded_at": recorded_at, "resolved": resolved}


def resolve_operation(operation_id, desk_checks, decision, explanation, recorded_by):
    """Mark one group operation and the incidents it caused as reviewed. Sends no command."""
    with transaction() as cursor:
        lock_review_state(cursor)
        cursor.execute(
            "SELECT review_state FROM group_operations WHERE operation_id = %s FOR UPDATE", (operation_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise ReviewError("Group operation not found", "not_found")
        if row[0] != "needs_review":
            raise ReviewError(
                f"This operation is not waiting for review (review state: {row[0]}). Nothing was changed.",
                "not_reviewable",
            )
        desk_ids = _operation_desk_ids(cursor, operation_id)
        _require_checked(desk_ids, desk_checks)
        _require_idle(cursor, desk_ids)
        # The record for the operation itself is written by _resolve_linked.
        resolved = _resolve_linked(cursor, [operation_id], decision, explanation, recorded_by, desk_checks)
        cursor.execute(
            "SELECT record_id, recorded_at FROM review_records "
            "WHERE subject_type = %s AND subject_id = %s AND action = 'resolved' "
            "ORDER BY record_id DESC LIMIT 1",
            (SUBJECT_OPERATION, operation_id),
        )
        record_id, recorded_at = cursor.fetchone()
    return {"record_id": record_id, "recorded_at": recorded_at, "resolved": resolved}


def resolve_incident(incident_id, desk_checks, decision, explanation, recorded_by):
    """Mark one cleared desk incident as reviewed. An incident that is still active cannot be resolved."""
    with transaction() as cursor:
        lock_review_state(cursor)
        cursor.execute(
            "SELECT desk_id, review_state, cleared_at FROM desk_incidents WHERE incident_id = %s FOR UPDATE",
            (incident_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise ReviewError("Desk incident not found", "not_found")
        desk_id, review_state, cleared_at = row
        if review_state != "needs_review":
            raise ReviewError(
                f"This incident is not waiting for review (review state: {review_state}). Nothing was changed.",
                "not_reviewable",
            )
        if cleared_at is None:
            raise ReviewError(
                "The fault is still active. An incident can be resolved only after the desk has "
                "reported no fault. Nothing was changed.",
                "desk_not_ready",
            )
        _require_checked([desk_id], desk_checks)
        _require_idle(cursor, [desk_id])
        cursor.execute(
            """
            UPDATE desk_incidents SET review_state = 'resolved', reviewed_at = CURRENT_TIMESTAMP
            WHERE incident_id = %s AND review_state = 'needs_review'
            """,
            (incident_id,),
        )
        record_id, recorded_at = _add_record(
            cursor, SUBJECT_INCIDENT, incident_id, "resolved", decision, explanation, recorded_by, desk_checks,
        )
    return {"record_id": record_id, "recorded_at": recorded_at,
            "resolved": {"cleaning_runs": [], "group_operations": [], "desk_incidents": [incident_id]}}


def acknowledge_incident(incident_id, note, recorded_by):
    """Record that a person has seen the fault. Nothing else changes.

    It does not take the review lock: it changes neither the review state nor whether
    the fault is cleared, so it can never unblock a start."""
    with transaction() as cursor:
        cursor.execute(
            """
            UPDATE desk_incidents
            SET acknowledged_at = COALESCE(acknowledged_at, CURRENT_TIMESTAMP)
            WHERE incident_id = %s AND review_state = 'needs_review'
            RETURNING acknowledged_at
            """,
            (incident_id,),
        )
        row = cursor.fetchone()
        if row is None:
            cursor.execute("SELECT review_state FROM desk_incidents WHERE incident_id = %s", (incident_id,))
            found = cursor.fetchone()
            if found is None:
                raise ReviewError("Desk incident not found", "not_found")
            raise ReviewError(
                "This incident has already been resolved. Nothing was changed.", "not_reviewable",
            )
        record_id, recorded_at = _add_record(
            cursor, SUBJECT_INCIDENT, incident_id, "acknowledged", None, note, recorded_by, None,
        )
    return {"record_id": record_id, "recorded_at": recorded_at, "acknowledged_at": row[0]}


# ---------- reading ----------

def list_unresolved(desk_id=None):
    """Every run, operation and incident waiting for review, and the desks that block starts.

    Runs and operations that need review always block. An incident blocks as described in
    block_on_every_unresolved_incident; each one says so in `blocks_starts`."""
    with transaction() as cursor:
        cursor.execute(
            """
            SELECT r.run_id, r.schedule_id, s.name, r.occurrence_date, r.status,
                   r.raise_operation_id, r.return_operation_id, r.updated_at
            FROM cleaning_runs AS r
            JOIN cleaning_schedules AS s ON s.schedule_id = r.schedule_id
            WHERE r.status = 'needs_review'
            ORDER BY r.run_id
            """
        )
        runs = []
        for run_id, schedule_id, name, day, status, raise_id, return_id, updated in cursor.fetchall():
            runs.append({
                "run_id": run_id, "schedule_id": schedule_id, "schedule_name": name,
                "occurrence_date": day, "status": status,
                "raise_operation_id": raise_id, "return_operation_id": return_id, "updated_at": updated,
            })
        for run in runs:
            run["desk_ids"] = _run_desk_ids(cursor, run["run_id"])

        cursor.execute(
            """
            SELECT o.operation_id, o.reason, o.state, o.finished_at,
                   COALESCE(array_agg(d.desk_id ORDER BY d.desk_id) FILTER (WHERE d.desk_id IS NOT NULL), '{}')
            FROM group_operations AS o
            LEFT JOIN group_operation_desks AS d ON d.operation_id = o.operation_id
            WHERE o.review_state = 'needs_review'
            GROUP BY o.operation_id, o.reason, o.state, o.finished_at, o.created_at
            ORDER BY o.created_at, o.operation_id
            """
        )
        operations = [
            {"operation_id": op_id, "reason": reason, "state": state, "finished_at": finished, "desk_ids": desks}
            for op_id, reason, state, finished, desks in cursor.fetchall()
        ]

        cursor.execute(
            """
            SELECT incident_id, desk_id, fault_category, first_seen_at, last_seen_at, cleared_at,
                   acknowledged_at, operation_id
            FROM desk_incidents WHERE review_state = 'needs_review'
            ORDER BY incident_id
            """
        )
        strict = block_on_every_unresolved_incident()
        incidents = [
            {"incident_id": i, "desk_id": desk, "fault_category": cat, "first_seen_at": first,
             "last_seen_at": last, "cleared_at": cleared, "acknowledged_at": ack, "operation_id": op,
             "blocks_starts": incident_blocks_starts(cleared is None, op, strict)}
            for i, desk, cat, first, last, cleared, ack, op in cursor.fetchall()
        ]

    if desk_id is not None:
        runs = [item for item in runs if desk_id in item["desk_ids"]]
        operations = [item for item in operations if desk_id in item["desk_ids"]]
        incidents = [item for item in incidents if item["desk_id"] == desk_id]
    blocking = sorted({
        *(desk for item in runs for desk in item["desk_ids"]),
        *(desk for item in operations for desk in item["desk_ids"]),
        *(item["desk_id"] for item in incidents if item["blocks_starts"]),
    })
    return {"cleaning_runs": runs, "group_operations": operations, "desk_incidents": incidents,
            "blocking_desk_ids": blocking}


def list_records(subject_type=None, subject_id=None, limit=50):
    query = (
        "SELECT record_id, subject_type, subject_id, action, decision, explanation, "
        "recorded_by, desk_checks, recorded_at FROM review_records WHERE TRUE"
    )
    parameters = []
    if subject_type is not None:
        query += " AND subject_type = %s"
        parameters.append(subject_type)
    if subject_id is not None:
        query += " AND subject_id = %s"
        parameters.append(str(subject_id))
    query += " ORDER BY record_id DESC LIMIT %s"
    parameters.append(limit)
    with transaction() as cursor:
        cursor.execute(query, parameters)
        names = [column[0] for column in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]
