"""PostgreSQL storage for S5-2 cleaning schedules and runs."""

from ..Domain.cleaning_schedule_validation import schedules_overlap
from .database import transaction


class ScheduleConflictError(Exception):
    """Two enabled schedules would control a desk at overlapping times."""


class ScheduleBusyError(Exception):
    """A schedule cannot be edited while its run needs attention."""


def _lock_schedule_changes(cursor):
    """Serialize schedule edits so simultaneous HTTP requests cannot bypass conflict checks."""
    cursor.execute("SELECT pg_advisory_xact_lock(52002, 1)")


def _check_conflicts(cursor, desk_ids, start_time, end_time, ignore_id=None):
    cursor.execute(
        """
        SELECT DISTINCT s.schedule_id, s.start_time, s.end_time, s.timezone
        FROM cleaning_schedules AS s
        JOIN cleaning_schedule_desks AS sd ON sd.schedule_id = s.schedule_id
        WHERE s.is_enabled = TRUE
          AND sd.desk_id = ANY(%s)
          AND (%s IS NULL OR s.schedule_id <> %s)
        """,
        (desk_ids, ignore_id, ignore_id),
    )
    for schedule_id, existing_start, existing_end, existing_zone in cursor.fetchall():
        if existing_zone != "Europe/Copenhagen" or schedules_overlap(
            start_time, end_time, existing_start, existing_end
        ):
            raise ScheduleConflictError(f"Conflicts with schedule {schedule_id}")


def create_schedule(
    name, cleaning_height_mm, return_height_mm, start_time, end_time, timezone, desk_ids,
    is_enabled=True,
):
    """Create a schedule together with its desks in one transaction."""
    with transaction() as cursor:
        _lock_schedule_changes(cursor)
        if is_enabled:
            _check_conflicts(cursor, desk_ids, start_time, end_time)
        cursor.execute(
            """
            INSERT INTO cleaning_schedules (
                name, cleaning_height_mm, return_height_mm,
                start_time, end_time, timezone, is_enabled
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING schedule_id
            """,
            (name, cleaning_height_mm, return_height_mm, start_time, end_time, timezone, is_enabled),
        )
        schedule_id = cursor.fetchone()[0]
        for desk_id in desk_ids:
            cursor.execute(
                "INSERT INTO cleaning_schedule_desks (schedule_id, desk_id) VALUES (%s, %s)",
                (schedule_id, desk_id),
            )
    return schedule_id


def _read_schedule(cursor, schedule_id):
    cursor.execute("SELECT * FROM cleaning_schedules WHERE schedule_id = %s", (schedule_id,))
    row = cursor.fetchone()
    if row is None:
        return None
    columns = [column[0] for column in cursor.description]
    result = dict(zip(columns, row))
    cursor.execute(
        "SELECT desk_id FROM cleaning_schedule_desks WHERE schedule_id = %s ORDER BY desk_id",
        (schedule_id,),
    )
    result["desk_ids"] = [item[0] for item in cursor.fetchall()]
    return result


def get_schedule(schedule_id):
    with transaction() as cursor:
        return _read_schedule(cursor, schedule_id)


def list_schedules():
    with transaction() as cursor:
        cursor.execute("SELECT schedule_id FROM cleaning_schedules ORDER BY schedule_id")
        ids = [row[0] for row in cursor.fetchall()]
        return [_read_schedule(cursor, schedule_id) for schedule_id in ids]


def _has_active_run(cursor, schedule_id):
    cursor.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM cleaning_runs
            WHERE schedule_id = %s
              AND status IN ('raising', 'cleaning', 'returning', 'needs_review')
        )
        """,
        (schedule_id,),
    )
    return cursor.fetchone()[0]


def schedule_has_active_run(schedule_id):
    with transaction() as cursor:
        return _has_active_run(cursor, schedule_id)


def update_schedule(
    schedule_id, name, cleaning_height_mm, return_height_mm,
    start_time, end_time, timezone, desk_ids,
    is_enabled=None,
):
    """Update safely: lock the schedule and reject edits while a run is active."""
    with transaction() as cursor:
        _lock_schedule_changes(cursor)
        cursor.execute(
            "SELECT is_enabled FROM cleaning_schedules WHERE schedule_id = %s FOR UPDATE",
            (schedule_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return False
        if _has_active_run(cursor, schedule_id):
            raise ScheduleBusyError("Cannot edit a schedule with an active or uncertain cleaning run")
        enabled = row[0] if is_enabled is None else is_enabled
        if enabled:
            _check_conflicts(cursor, desk_ids, start_time, end_time, ignore_id=schedule_id)

        cursor.execute(
            """
            UPDATE cleaning_schedules
            SET name = %s, cleaning_height_mm = %s, return_height_mm = %s,
                start_time = %s, end_time = %s, timezone = %s, is_enabled = %s
            WHERE schedule_id = %s
            """,
            (name, cleaning_height_mm, return_height_mm,
             start_time, end_time, timezone, enabled, schedule_id),
        )
        cursor.execute(
            "DELETE FROM cleaning_schedule_desks WHERE schedule_id = %s", (schedule_id,)
        )
        for desk_id in desk_ids:
            cursor.execute(
                "INSERT INTO cleaning_schedule_desks (schedule_id, desk_id) VALUES (%s, %s)",
                (schedule_id, desk_id),
            )
    return True


def disable_schedule(schedule_id):
    """Disable future starts, without stopping the currently active run."""
    with transaction() as cursor:
        cursor.execute(
            """
            UPDATE cleaning_schedules SET is_enabled = FALSE
            WHERE schedule_id = %s RETURNING schedule_id
            """,
            (schedule_id,),
        )
        return cursor.fetchone() is not None


def list_cleaning_runs():
    # keep the newest runs at the top
    with transaction() as cursor:
        cursor.execute(
            """
            SELECT r.*, s.name AS schedule_name, s.timezone
            FROM cleaning_runs AS r
            JOIN cleaning_schedules AS s ON s.schedule_id = r.schedule_id
            ORDER BY r.occurrence_date DESC, r.run_id DESC
            """
        )
        names = [column[0] for column in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]


def claimed_occurrence_dates(schedule_id, since):
    with transaction() as cursor:
        cursor.execute(
            "SELECT occurrence_date FROM cleaning_runs WHERE schedule_id = %s AND occurrence_date >= %s",
            (schedule_id, since),
        )
        return {row[0] for row in cursor.fetchall()}


def claim_cleaning_start(schedule_id, occurrence_date, scheduled_start_utc=None):
    """Claim one daily start. Lock schedule to serialize with edits and disable."""
    with transaction() as cursor:
        cursor.execute(
            """
            SELECT is_enabled, created_at FROM cleaning_schedules
            WHERE schedule_id = %s FOR UPDATE
            """,
            (schedule_id,),
        )
        schedule = cursor.fetchone()
        if schedule is None or not schedule[0]:
            return None
        # A schedule created after today's start must not move immediately.
        if scheduled_start_utc is not None and schedule[1] > scheduled_start_utc:
            return None
        cursor.execute(
            """
            INSERT INTO cleaning_runs (schedule_id, occurrence_date, status)
            VALUES (%s, %s, 'raising')
            ON CONFLICT (schedule_id, occurrence_date) DO NOTHING
            RETURNING run_id
            """,
            (schedule_id, occurrence_date),
        )
        row = cursor.fetchone()
        return row[0] if row else None


def claim_missed_start(schedule_id, occurrence_date, scheduled_start_utc):
    """Record a missed start for review, never perform a catch-up movement."""
    with transaction() as cursor:
        cursor.execute(
            """
            SELECT is_enabled, created_at FROM cleaning_schedules
            WHERE schedule_id = %s FOR UPDATE
            """,
            (schedule_id,),
        )
        schedule = cursor.fetchone()
        if schedule is None or not schedule[0] or schedule[1] > scheduled_start_utc:
            return None
        cursor.execute(
            """
            INSERT INTO cleaning_runs (schedule_id, occurrence_date, status)
            VALUES (%s, %s, 'needs_review')
            ON CONFLICT (schedule_id, occurrence_date) DO NOTHING
            RETURNING run_id
            """,
            (schedule_id, occurrence_date),
        )
        row = cursor.fetchone()
        return row[0] if row else None


def claim_cleaning_return(schedule_id, occurrence_date):
    """Claim a return exactly once, and only after a confirmed successful raise."""
    with transaction() as cursor:
        cursor.execute(
            """
            UPDATE cleaning_runs
            SET status = 'returning', updated_at = CURRENT_TIMESTAMP
            WHERE schedule_id = %s AND occurrence_date = %s
              AND status = 'cleaning'
            RETURNING run_id
            """,
            (schedule_id, occurrence_date),
        )
        row = cursor.fetchone()
        return row[0] if row else None


def save_raise_operation(run_id, operation_id):
    with transaction() as cursor:
        cursor.execute(
            """
            UPDATE cleaning_runs
            SET raise_operation_id = %s, raise_requested_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE run_id = %s AND status = 'raising'
              AND raise_operation_id IS NULL RETURNING run_id
            """,
            (operation_id, run_id),
        )
        return cursor.fetchone() is not None


def save_return_operation(run_id, operation_id):
    with transaction() as cursor:
        cursor.execute(
            """
            UPDATE cleaning_runs
            SET return_operation_id = %s, return_requested_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE run_id = %s AND status = 'returning'
              AND return_operation_id IS NULL RETURNING run_id
            """,
            (operation_id, run_id),
        )
        return cursor.fetchone() is not None


def set_run_status(run_id, old_status, new_status):
    """Compare-and-set prevents stale workers from overwriting another action."""
    with transaction() as cursor:
        cursor.execute(
            """
            UPDATE cleaning_runs SET status = %s, updated_at = CURRENT_TIMESTAMP
            WHERE run_id = %s AND status = %s RETURNING run_id
            """,
            (new_status, run_id, old_status),
        )
        return cursor.fetchone() is not None


def get_cleaning_run(run_id):
    with transaction() as cursor:
        cursor.execute(
            """
            SELECT run_id, status, raise_operation_id, return_operation_id
            FROM cleaning_runs WHERE run_id = %s
            """,
            (run_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(zip(
            ("run_id", "status", "raise_operation_id", "return_operation_id"), row
        ))


def get_active_movement_runs():
    with transaction() as cursor:
        cursor.execute(
            """
            SELECT run_id, status, raise_operation_id, return_operation_id
            FROM cleaning_runs WHERE status IN ('raising', 'returning')
            ORDER BY run_id
            """
        )
        names = ("run_id", "status", "raise_operation_id", "return_operation_id")
        return [dict(zip(names, row)) for row in cursor.fetchall()]


def get_unfinished_runs():
    """Include 'cleaning' so overdue returns can be reviewed safely."""
    with transaction() as cursor:
        cursor.execute(
            """
            SELECT r.run_id, r.occurrence_date, r.status,
                   s.start_time, s.end_time, s.timezone
            FROM cleaning_runs AS r
            JOIN cleaning_schedules AS s ON s.schedule_id = r.schedule_id
            WHERE r.status IN ('raising', 'cleaning', 'returning')
            """
        )
        names = ("run_id", "occurrence_date", "status", "start_time", "end_time", "timezone")
        return [dict(zip(names, row)) for row in cursor.fetchall()]


def mark_interrupted_runs():
    """S5-1 operation state is in memory. Never replay it after a restart."""
    with transaction() as cursor:
        cursor.execute(
            """
            UPDATE cleaning_runs
            SET status = 'needs_review', updated_at = CURRENT_TIMESTAMP
            WHERE status IN ('raising', 'cleaning', 'returning')
            """
        )
        return cursor.rowcount
