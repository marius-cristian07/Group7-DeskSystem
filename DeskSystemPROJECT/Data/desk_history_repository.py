
"""Read historical desk measurements and commands from PostgreSQL."""

from .database import transaction


def get_desk_readings(desk_id, start=None, end=None, limit=50):
    """Retrieve saved readings and their errors, newest first."""

    query = """
        SELECT
            reading_id,
            desk_id,
            recorded_at,
            position_mm,
            speed_mms,
            status
        FROM desk_readings
        WHERE desk_id = %s
    """

    parameters = [desk_id]

    if start is not None:
        query += " AND recorded_at >= %s"
        parameters.append(start)

    if end is not None:
        query += " AND recorded_at <= %s"
        parameters.append(end)

    query += " ORDER BY recorded_at DESC, reading_id DESC LIMIT %s"
    parameters.append(limit)

    with transaction() as cursor:
        cursor.execute(query, parameters)

        columns = [column[0] for column in cursor.description]
        rows = cursor.fetchall()

        readings = [dict(zip(columns, row)) for row in rows]

        for reading in readings:
            reading["errors"] = []

        if readings:
            reading_ids = [
                reading["reading_id"] for reading in readings
            ]

            cursor.execute(
                """
                SELECT
                    reading_id,
                    error_index,
                    time_s,
                    error_code
                FROM desk_errors
                WHERE reading_id = ANY(%s)
                ORDER BY reading_id, error_index
                """,
                (reading_ids,),
            )

            errors_by_reading = {
                reading_id: [] for reading_id in reading_ids
            }

            for reading_id, error_index, time_s, error_code in cursor.fetchall():
                errors_by_reading[reading_id].append({
                    "error_index": error_index,
                    "time_s": time_s,
                    "error_code": error_code,
                })

            for reading in readings:
                reading["errors"] = errors_by_reading[
                    reading["reading_id"]
                ]

    return readings


def get_desk_commands(desk_id, start=None, end=None, limit=50):
    """Retrieve saved movement commands for one desk, newest first."""

    query = """
        SELECT
            command_id,
            desk_id,
            requested_at,
            target_position_mm,
            status
        FROM desk_commands
        WHERE desk_id = %s
    """

    parameters = [desk_id]

    if start is not None:
        query += " AND requested_at >= %s"
        parameters.append(start)

    if end is not None:
        query += " AND requested_at <= %s"
        parameters.append(end)

    query += " ORDER BY requested_at DESC, command_id DESC LIMIT %s"
    parameters.append(limit)

    with transaction() as cursor:
        cursor.execute(query, parameters)

        columns = [column[0] for column in cursor.description]
        rows = cursor.fetchall()

    return [dict(zip(columns, row)) for row in rows]
