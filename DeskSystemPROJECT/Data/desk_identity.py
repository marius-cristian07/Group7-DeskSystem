# Keep one desk identity row containing its ID, name, and manufacturer.
# Both repositories use this helper because readings and commands reference that row.
# The caller supplies the cursor, so this update belongs to the caller's transaction.

"""The desk row used by both readings and movement commands."""


def upsert_desk(cursor, desk_record):
    # Use the caller's cursor so the identity and reading share one transaction.
    config = desk_record["config"]
    # ON CONFLICT updates an existing desk; EXCLUDED holds the incoming values.
    cursor.execute(
        """
        INSERT INTO desk (desk_id, name, manufacturer)
        VALUES (%s, %s, %s)
        ON CONFLICT (desk_id) DO UPDATE
        SET name = EXCLUDED.name, manufacturer = EXCLUDED.manufacturer;
        """,
        (desk_record["desk_id"], config["name"], config["manufacturer"]),
    )
