"""Optional real PostgreSQL smoke test. Creates/deletes ONLY its temporary S5-2 data."""

from datetime import date, time

from DeskSystemPROJECT.Data import cleaning_schedule_repository as repo
from DeskSystemPROJECT.Data.database import transaction

DESK = "cd:fb:1a:53:fb:e6"
created = []


def create(name, start, end):
    result = repo.create_schedule(
        name, 1200, 720, start, end, "Europe/Copenhagen", [DESK],
    )
    created.append(result)
    return result


try:
    occupied = [s["schedule_id"] for s in repo.list_schedules()
                if s["is_enabled"] and DESK in s["desk_ids"]]
    if occupied:
        raise RuntimeError(
            f"Existing enabled schedules use the test desk: {occupied}. "
            "Not altering them. Use a separate test desk or disable them manually."
        )

    night = create("S5-2 DB smoke: night", time(22), time(6))
    assert repo.get_schedule(night)["name"] == "S5-2 DB smoke: night"
    print("PASS: Schedule persisted")

    try:
        create("S5-2 DB smoke: overlap", time(23), time(2))
    except repo.ScheduleConflictError:
        print("PASS: Overlapping schedule rejected")
    else:
        raise AssertionError("Conflict was not detected")

    day = create("S5-2 DB smoke: day", time(10), time(12))
    try:
        repo.update_schedule(day, "Invalid edit", 1200, 720, time(23), time(2),
                             "Europe/Copenhagen", [DESK])
    except repo.ScheduleConflictError:
        print("PASS: Overlapping PUT rejected")
    else:
        raise AssertionError("Conflicting update accepted")
    assert repo.get_schedule(day)["name"] == "S5-2 DB smoke: day"

    run_date = date(2031, 11, 17)  # No actual movements; scheduler should remain disabled.
    run_id = repo.claim_cleaning_start(night, run_date)
    assert run_id is not None
    assert repo.claim_cleaning_start(night, run_date) is None
    assert repo.claim_cleaning_return(night, run_date) is None
    print("PASS: Unique start and blocked early return")

    assert repo.save_raise_operation(run_id, "smoke-test-operation") is True
    assert repo.save_raise_operation(run_id, "unexpected-second-operation") is False
    assert repo.get_cleaning_run(run_id)["raise_operation_id"] == "smoke-test-operation"
    print("PASS: Operation ID saved once")

    try:
        repo.update_schedule(night, "Unsafe edit", 1200, 720, time(22), time(6),
                             "Europe/Copenhagen", [DESK])
    except repo.ScheduleBusyError:
        print("PASS: Active schedule cannot be edited")
    else:
        raise AssertionError("Active schedule update was accepted")

    assert repo.set_run_status(run_id, "raising", "cleaning")
    assert repo.disable_schedule(night)
    assert repo.claim_cleaning_return(night, run_date) == run_id
    assert repo.claim_cleaning_return(night, run_date) is None
    assert repo.set_run_status(run_id, "returning", "completed")
    print("PASS: Return after disable, once per occurrence")
    print("ALL DATABASE SMOKE TESTS PASSED")

finally:
    if created:
        with transaction() as cursor:
            for schedule_id in created:
                cursor.execute("DELETE FROM cleaning_runs WHERE schedule_id = %s", (schedule_id,))
                cursor.execute("DELETE FROM cleaning_schedules WHERE schedule_id = %s", (schedule_id,))
        print("Temporary schedules/runs deleted; existing data unchanged")
