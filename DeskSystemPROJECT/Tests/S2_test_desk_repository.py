import pytest

from Data.desk_repository import DatabaseError, save_desk


@pytest.fixture
def desk_record():
    return {
        "desk_id": "test-desk-001",
        "config": {"name": "Test desk", "manufacturer": "LINAK"},
        "state": {
            "position_mm": 720,
            "speed_mms": 0,
            "status": "Normal",
            "isPositionLost": False,
            "isOverloadProtectionUp": False,
            "isOverloadProtectionDown": False,
            "isAntiCollision": False,
        },
        "usage": {"activationsCounter": 12, "sitStandCounter": 4},
        "lastErrors": [{"time_s": 123, "errorCode": 93}],
    }


def test_new_desk_and_second_reading_do_not_duplicate_desk(
    desk_record, query_test_db
):
    first_reading_id = save_desk(desk_record)

    # Same desk, but updated metadata and a different observation.
    second_record = {
        **desk_record,
        "config": {"name": "Updated desk name", "manufacturer": "LINAK"},
        "state": {**desk_record["state"], "position_mm": 900},
        "lastErrors": [],
    }
    second_reading_id = save_desk(second_record)

    assert second_reading_id != first_reading_id
    assert query_test_db("SELECT COUNT(*) FROM desk;") == [(1,)]
    assert query_test_db(
        "SELECT name, manufacturer FROM desk WHERE desk_id = %s;",
        (desk_record["desk_id"],),
    ) == [("Updated desk name", "LINAK")]
    assert query_test_db(
        "SELECT position_mm FROM desk_readings "
        "WHERE desk_id = %s ORDER BY reading_id;",
        (desk_record["desk_id"],),
    ) == [(720,), (900,)]

    # Errors belong to the reading that contained them, not just to the desk.
    assert query_test_db(
        "SELECT e.time_s, e.error_code FROM desk_errors e "
        "WHERE e.reading_id = %s;",
        (first_reading_id,),
    ) == [(123, 93)]
    assert query_test_db(
        "SELECT COUNT(*) FROM desk_errors WHERE reading_id = %s;",
        (second_reading_id,),
    ) == [(0,)]


def test_failed_error_insert_rolls_back_desk_and_reading(desk_record, query_test_db):
    # errorCode is an integer column. This invalid value makes PostgreSQL reject
    # the final insert, after the desk and reading inserts have been attempted.
    broken_record = {
        **desk_record,
        "lastErrors": [{"time_s": 123, "errorCode": "not-an-integer"}],
    }

    with pytest.raises(DatabaseError):
        save_desk(broken_record)

    assert query_test_db("SELECT COUNT(*) FROM desk;") == [(0,)]
    assert query_test_db("SELECT COUNT(*) FROM desk_readings;") == [(0,)]
    assert query_test_db("SELECT COUNT(*) FROM desk_errors;") == [(0,)]