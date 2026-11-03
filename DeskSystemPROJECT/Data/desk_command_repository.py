# Store the outcome of a request to move a desk in PostgreSQL.
# The workflow sends the request first, then records its requested height and status here.
# An accepted command records the simulator's reply, not proof that the desk reached its target.

"""Store movement requests without treating acceptance as a completed move."""

from .database import transaction
from .desk_identity import upsert_desk

STATUS_ACCEPTED = "accepted"
STATUS_FAILED = "failed"
VALID_STATUSES = (STATUS_ACCEPTED, STATUS_FAILED)


def desk_exists(desk_id):
    with transaction() as cursor:
        # A single-column tuple supplies the query parameter, even for one ID.
        cursor.execute("SELECT 1 FROM desk WHERE desk_id = %s;", (desk_id,))
        return cursor.fetchone() is not None


def save_desk_identity(desk_record):
    """Create the desk needed by the command's foreign key, without a reading."""
    with transaction() as cursor:
        upsert_desk(cursor, desk_record)


def save_command(desk_id, target_position_mm, status):
    """Record the requested height, even when the simulator clamps its target."""
    if status not in VALID_STATUSES:
        raise ValueError(f"Command status must be one of {VALID_STATUSES}")
    with transaction() as cursor:
        cursor.execute(
            """
            INSERT INTO desk_commands (desk_id, target_position_mm, status)
            VALUES (%s, %s, %s)
            RETURNING command_id;
            """,
            (desk_id, target_position_mm, status),
        )
        return cursor.fetchone()[0]
