import os

import psycopg2


class DatabaseError(Exception):
    """Raised when the database is unavailable or a query fails."""


def get_database_connection():
    """Create and return a PostgreSQL connection using the DATABASE_URL value."""
    # This keeps the password and server details out of the code file.
    # Example value: postgresql://user:password@localhost:5432/mydatabase
    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        raise DatabaseError(
            "DATABASE_URL is not set. Add it before saving desk data."
        )

    try:
        return psycopg2.connect(database_url)
    except psycopg2.Error as err:
        raise DatabaseError(f"Failed to connect to PostgreSQL: {err}") from None


def save_desk(desk_record):
    """
    Save one desk snapshot returned by the desk API.

    This function saves the desk in 3 parts:
    - desk: basic desk info such as name and manufacturer
    - desk_readings: current position, speed, state, and counters
    - desk_errors: any errors reported with that reading

    Everything is saved in one database transaction:
    if one part fails, the whole save is rolled back.
    """
    conn = get_database_connection()

    try:
        # The with block starts a transaction automatically.
        # If everything succeeds, PostgreSQL commits it for us.
        # If an error happens, it rolls back instead of saving partial data.
        with conn, conn.cursor() as cursor:
            desk_id = desk_record["desk_id"]
            config = desk_record["config"]

            # Insert the desk row, or update it if that desk already exists.
            # desk_id is the unique key, so it is used to detect a match.
            cursor.execute(
                """
                INSERT INTO desk (desk_id, name, manufacturer)
                VALUES (%s, %s, %s)
                ON CONFLICT (desk_id) DO UPDATE
                SET name = EXCLUDED.name,
                    manufacturer = EXCLUDED.manufacturer;
                """,
                (desk_id, config["name"], config["manufacturer"]),
            )

            # Pull out the current state and usage information for this reading.
            state = desk_record["state"]
            usage = desk_record["usage"]

            # Save one new reading snapshot for this desk.
            cursor.execute(
                """
                INSERT INTO desk_readings (
                    desk_id,
                    position_mm,
                    speed_mms,
                    status,
                    activations_counter,
                    sit_stand_counter,
                    is_position_lost,
                    is_overload_protection_up,
                    is_overload_protection_down,
                    is_anti_collision
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING reading_id;
                """,
                (
                    desk_id,
                    state["position_mm"],
                    state["speed_mms"],
                    state["status"],
                    usage["activationsCounter"],
                    usage["sitStandCounter"],
                    state["isPositionLost"],
                    state["isOverloadProtectionUp"],
                    state["isOverloadProtectionDown"],
                    state["isAntiCollision"],
                ),
            )

            # PostgreSQL creates a new reading_id automatically.
            # We need it so each error can be linked to the correct reading.
            reading_id = cursor.fetchone()[0]

            # Save each error in the lastErrors list.
            # The index is stored too, so the original order is not lost.
            errors = desk_record.get("lastErrors", [])
            for index, error_entry in enumerate(errors):
                cursor.execute(
                    """
                    INSERT INTO desk_errors (
                        reading_id,
                        error_index,
                        time_s,
                        error_code
                    )
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (reading_id, error_index) DO NOTHING;
                    """,
                    (
                        reading_id,
                        index,
                        error_entry["time_s"],
                        error_entry["errorCode"],
                    ),
                )

        # Return the created reading ID so the caller knows which snapshot was saved.
        return reading_id

    except psycopg2.Error as err:
        raise DatabaseError(f"Database operation failed: {err}") from None

    finally:
        # Always close the connection when we are done.
        # This is important so the app does not leave open database connections.
        conn.close()