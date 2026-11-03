# Save a validated simulator record as a historical snapshot in PostgreSQL.
# save_desk updates the desk identity, inserts a new reading, then attaches its errors.
# It returns the new reading ID. Repeated syncs add readings for the same desk.

"""Save desk readings and their errors in PostgreSQL."""

from .database import transaction
from .desk_identity import upsert_desk


def save_desk(desk_record):
    """Save the desk, reading, and errors together, or roll back all of them."""
    with transaction() as cursor:
        upsert_desk(cursor, desk_record)
        state = desk_record["state"]
        usage = desk_record["usage"]
        # Parameters follow the column order below and are passed separately from SQL.
        cursor.execute(
            """
            INSERT INTO desk_readings (
                desk_id, position_mm, speed_mms, status,
                activations_counter, sit_stand_counter, is_position_lost,
                is_overload_protection_up, is_overload_protection_down,
                is_anti_collision
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING reading_id;
            """,
            (
                desk_record["desk_id"], state["position_mm"], state["speed_mms"],
                state["status"], usage["activationsCounter"], usage["sitStandCounter"],
                state["isPositionLost"], state["isOverloadProtectionUp"],
                state["isOverloadProtectionDown"], state["isAntiCollision"],
            ),
        )
        # RETURNING gives us the ID needed to link this snapshot to its errors.
        reading_id = cursor.fetchone()[0]

        # Keep error order and attach every error to this particular reading.
        for index, error in enumerate(desk_record.get("lastErrors", [])):
            cursor.execute(
                """
                INSERT INTO desk_errors (reading_id, error_index, time_s, error_code)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (reading_id, error_index) DO NOTHING;
                """,
                (reading_id, index, error["time_s"], error["errorCode"]),
            )
    return reading_id
