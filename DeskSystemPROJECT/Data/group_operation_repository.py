"""Persistent storage for group operations and desk results."""

from .database import transaction
from .review_repository import lock_review_state


_OPERATION_COLUMNS = (
    "operation_id",
    "reason",
    "target_position_mm",
    "state",
    "required_channels",
    "created_at",
    "dispatched_at",
    "finished_at",
    "blocked_code",
    "blocked_message",
    "review_state",
)

_DESK_COLUMNS = (
    "desk_id",
    "result",
    "detail",
    "command_id",
    "command_status",
    "accepted_position_mm",
    "last_position_mm",
    "last_speed_mms",
    "last_status",
    "last_observed_at",
    "fault_codes",
    "at_target",
)

_ACTIVE = (
    "pending_warning",
    "countdown",
    "dispatching",
    "monitoring",
)


def _upsert_operation(cursor, operation):
    names = ", ".join(_OPERATION_COLUMNS)
    updates = ", ".join(
        f"{name} = EXCLUDED.{name}"
        for name in _OPERATION_COLUMNS[1:]
    )

    cursor.execute(
        f"""
        INSERT INTO group_operations ({names})
        VALUES ({", ".join(["%s"] * len(_OPERATION_COLUMNS))})
        ON CONFLICT (operation_id) DO UPDATE
        SET {updates}, updated_at = CURRENT_TIMESTAMP
        """,
        [operation[name] for name in _OPERATION_COLUMNS],
    )


def _upsert_desk(cursor, operation_id, desk):
    names = ", ".join(_DESK_COLUMNS)
    updates = ", ".join(
        f"{name} = EXCLUDED.{name}"
        for name in _DESK_COLUMNS[1:]
    )

    cursor.execute(
        f"""
        INSERT INTO group_operation_desks (operation_id, {names})
        VALUES (%s, {", ".join(["%s"] * len(_DESK_COLUMNS))})
        ON CONFLICT (operation_id, desk_id) DO UPDATE
        SET {updates}, updated_at = CURRENT_TIMESTAMP
        """,
        [operation_id, *(desk[name] for name in _DESK_COLUMNS)],
    )


def save_operation(operation, desks=()):
    """Save an operation and its desk results in one transaction."""
    with transaction() as cursor:
        # S6-3: a manager's resolution and an automatic cleaning start take this lock exclusively,
        # so neither can commit while an operation for the same desks is being written.
        lock_review_state(cursor, shared=True)
        _upsert_operation(cursor, operation)

        for desk in desks:
            _upsert_desk(cursor, operation["operation_id"], desk)


def record_dispatch_intent(operation_id, desk_id):
    """Persist dispatch intent before sending a movement command."""
    with transaction() as cursor:
        cursor.execute(
            """
            UPDATE group_operation_desks
            SET dispatch_intent_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE operation_id = %s
              AND desk_id = %s
              AND dispatch_intent_at IS NULL
            RETURNING dispatch_intent_at
            """,
            (operation_id, desk_id),
        )

        row = cursor.fetchone()

    if row is None:
        raise LookupError(
            f"No unsent desk {desk_id} in operation {operation_id}"
        )

    return row[0]


def _rows(cursor):
    names = [column[0] for column in cursor.description]

    return [
        dict(zip(names, row))
        for row in cursor.fetchall()
    ]


def _with_desks(cursor, operations):
    if not operations:
        return []

    cursor.execute(
        """
        SELECT *
        FROM group_operation_desks
        WHERE operation_id = ANY(%s)
        ORDER BY operation_id, desk_id
        """,
        ([operation["operation_id"] for operation in operations],),
    )

    desks = {}

    for desk in _rows(cursor):
        desks.setdefault(desk["operation_id"], []).append(desk)

    return [
        (operation, desks.get(operation["operation_id"], []))
        for operation in operations
    ]


def load_operation(operation_id):
    """Return a saved operation and its desk results."""
    with transaction() as cursor:
        cursor.execute(
            """
            SELECT *
            FROM group_operations
            WHERE operation_id = %s
            """,
            (operation_id,),
        )

        found = _with_desks(cursor, _rows(cursor))

    return found[0] if found else None


def list_operations(limit, offset):
    """Return a page of saved operations, newest first."""
    with transaction() as cursor:
        cursor.execute(
            """
            SELECT *
            FROM group_operations
            ORDER BY created_at DESC, operation_id DESC
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
        )

        return _with_desks(cursor, _rows(cursor))


def mark_interrupted_operations():
    """Mark unfinished operations for review without resending commands."""
    with transaction() as cursor:
        cursor.execute(
            """
            SELECT operation_id
            FROM group_operations
            WHERE state = ANY(%s)
            FOR UPDATE
            """,
            (list(_ACTIVE),),
        )

        operation_ids = [row[0] for row in cursor.fetchall()]

        if not operation_ids:
            return []

        cursor.execute(
            """
            UPDATE group_operation_desks
            SET result = CASE
                    WHEN result = 'moving' THEN 'unverified'
                    WHEN dispatch_intent_at IS NOT NULL THEN 'unknown'
                    ELSE 'not_sent'
                END,
                detail = CASE
                    WHEN result = 'moving' THEN
                        'The command was accepted, but the backend stopped '
                        'before a fresh reading confirmed the target. '
                        'The final position is unknown. It was not resent.'
                    WHEN dispatch_intent_at IS NOT NULL THEN
                        'The backend stopped after this command may have '
                        'been sent. The desk may have moved. '
                        'The command was not retried; check the desk.'
                    ELSE
                        'Not sent: the backend stopped before this '
                        'command was sent.'
                END,
                updated_at = CURRENT_TIMESTAMP
            WHERE operation_id = ANY(%s)
              AND result IN ('pending', 'moving')
            """,
            (operation_ids,),
        )

        cursor.execute(
            """
            UPDATE group_operations
            SET state = 'interrupted',
                review_state = 'needs_review',
                finished_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP,
                blocked_code = 'interrupted_by_restart',
                blocked_message =
                    'The backend stopped before this operation finished '
                    '(last state: ' || state || '). '
                    'It was not resumed and needs review.'
            WHERE operation_id = ANY(%s)
            """,
            (operation_ids,),
        )

    return operation_ids