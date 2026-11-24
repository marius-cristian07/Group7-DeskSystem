"""Store and retrieve persistent desk incidents."""

from ..Domain.desk_faults import classify_faults
from .database import transaction


_ACTIVE_OPERATION_STATES = [
    "pending_warning",
    "countdown",
    "dispatching",
    "monitoring",
]


def observe_reading(cursor, desk_id, state, reading_id):
    """Update incidents within the reading transaction."""
    health = classify_faults(state)
    faults = list(health.faults)
    status = str((state or {}).get("status", "")).strip().lower()

    uncertain = status in (
        "", "unknown", "unavailable", "offline", "unreachable"
    )

    # An uncertain reading does not confirm recovery.
    if not uncertain and health.classification in ("healthy", "faulty"):
        cursor.execute(
            """
            UPDATE desk_incidents
            SET cleared_at = CURRENT_TIMESTAMP
            WHERE desk_id = %s
              AND cleared_at IS NULL
              AND NOT (fault_category = ANY(%s::text[]))
            """,
            (desk_id, faults),
        )

    for fault in faults:
        cursor.execute(
            """
            INSERT INTO desk_incidents (
                desk_id,
                fault_category,
                first_reading_id,
                last_reading_id,
                operation_id
            )
            VALUES (%s, %s, %s, %s, (
                SELECT o.operation_id
                FROM group_operations AS o
                JOIN group_operation_desks AS d
                    ON d.operation_id = o.operation_id
                WHERE d.desk_id = %s
                  AND o.state = ANY(%s)
                ORDER BY o.created_at DESC
                LIMIT 1
            ))
            ON CONFLICT (desk_id, fault_category)
            WHERE cleared_at IS NULL
            DO UPDATE SET
                last_seen_at = CURRENT_TIMESTAMP,
                last_reading_id = EXCLUDED.last_reading_id,
                observation_count = desk_incidents.observation_count + 1
            """,
            (
                desk_id,
                fault,
                reading_id,
                reading_id,
                desk_id,
                _ACTIVE_OPERATION_STATES,
            ),
        )


def list_incidents(
    desk_id=None,
    operation_id=None,
    active=None,
    limit=50,
    offset=0,
):
    """Return incidents with optional filters and pagination."""
    query = "SELECT * FROM desk_incidents WHERE TRUE"
    parameters = []

    if desk_id is not None:
        query += " AND desk_id = %s"
        parameters.append(desk_id)

    if operation_id is not None:
        query += " AND operation_id = %s"
        parameters.append(operation_id)

    if active is not None:
        query += (
            " AND cleared_at IS NULL"
            if active
            else " AND cleared_at IS NOT NULL"
        )

    query += """
        ORDER BY first_seen_at DESC, incident_id DESC
        LIMIT %s OFFSET %s
    """

    parameters += [limit, offset]

    with transaction() as cursor:
        cursor.execute(query, parameters)
        names = [column[0] for column in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]