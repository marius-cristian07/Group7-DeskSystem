"""S6-2: saved group operations, dispatch intent, incidents and startup recovery.

The first tests use an in-memory store and a mocked workflow. The PostgreSQL tests need
TEST_DATABASE_URL pointing at a disposable database whose name ends in _test (see
conftest.py); they are skipped otherwise. No test contacts a simulator or moves a desk.
"""

import copy
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from DeskSystemPROJECT.Data.database import DatabaseError
from DeskSystemPROJECT.Domain.desk_workflow import MoveResult
from DeskSystemPROJECT.Domain.group_operations import (
    BLOCKED, COMPLETED, GroupOperationError, GroupOperationService, GroupOperationSettings,
)
from DeskSystemPROJECT.group_operations_api import get_group_service, router
from DeskSystemPROJECT.Tests.fixtures import sample_desk

SETTINGS = GroupOperationSettings(
    countdown_s=10, ack_timeout_s=15, stale_s=15, required_channels=("dashboard",),
    monitor_timeout_s=5, monitor_poll_s=1,
)


class MemoryStore:
    """Behaves like Data/group_operation_repository for the service's purposes."""

    def __init__(self):
        self.operations, self.desks, self.log = {}, {}, []
        self.fail_intent = False
        self.fail_save = False

    def save_operation(self, operation, desks=()):
        if self.fail_save:
            raise DatabaseError("database down")
        self.operations[operation["operation_id"]] = dict(operation)
        for desk in desks:
            key = (operation["operation_id"], desk["desk_id"])
            intent = self.desks.get(key, {}).get("dispatch_intent_at")
            self.desks[key] = {**desk, "operation_id": key[0], "dispatch_intent_at": intent}

    def record_dispatch_intent(self, operation_id, desk_id):
        if self.fail_intent:
            raise DatabaseError("database down")
        self.log.append(("intent", desk_id))
        self.desks[(operation_id, desk_id)]["dispatch_intent_at"] = datetime.now(timezone.utc)

    def mark_interrupted_operations(self):
        return []

    def _desks_of(self, operation_id):
        return [copy.deepcopy(d) for (op, _), d in sorted(self.desks.items()) if op == operation_id]

    def load_operation(self, operation_id):
        if operation_id not in self.operations:
            return None
        return dict(self.operations[operation_id]), self._desks_of(operation_id)

    def list_operations(self, limit, offset):
        rows = sorted(self.operations.values(), key=lambda op: op["created_at"], reverse=True)
        return [(dict(op), self._desks_of(op["operation_id"])) for op in rows[offset:offset + limit]]


def at_target_record(desk_id, position=1000):
    record = sample_desk()
    record["desk_id"] = desk_id
    record["state"].update(position_mm=position, speed_mms=0)
    return record


def make_workflow(log, command_id=7):
    workflow = Mock()
    workflow.api.get_desk.side_effect = lambda _url, _key, desk_id: at_target_record(desk_id)

    def request_height(desk_id, target_mm):
        log.append(("send", desk_id))
        return MoveResult(desk_id, target_mm, "accepted", accepted_mm=target_mm,
                          command_id=command_id, outcome="moving")
    workflow.request_height.side_effect = request_height
    return workflow


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def make_service(store, workflow, clock=None, wall=1_800_000_000, recover=True):
    clock = clock or Clock()
    spawn = Mock()
    service = GroupOperationService(
        lambda: workflow, settings=SETTINGS, clock=clock, wall_clock=lambda: wall,
        sleep=lambda _s: None, spawn=spawn, store=store,
    )
    if recover:
        service.recover_interrupted()
    return service, clock, spawn


def run_to_dispatch(service, clock, spawn, desks=("desk-a", "desk-b")):
    """Create, acknowledge and pass the countdown, then run the dispatch worker inline."""
    operation = service.create(list(desks), 1000)
    service.acknowledge(operation.operation_id, "dashboard")
    clock.now = 10
    service.tick()
    function, *args = spawn.call_args.args
    function(*args)
    return operation.operation_id


class PersistenceWithMemoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.workflow = make_workflow(self.store.log)
        self.service, self.clock, self.spawn = make_service(self.store, self.workflow)

    def test_creation_transitions_and_final_desk_results_are_saved(self):
        operation_id = run_to_dispatch(self.service, self.clock, self.spawn)

        saved, desks = self.store.load_operation(operation_id)
        self.assertEqual(saved["state"], COMPLETED)
        self.assertEqual(saved["review_state"], "not_required")
        self.assertIsNotNone(saved["dispatched_at"])
        self.assertEqual([d["result"] for d in desks], ["reached", "reached"])
        self.assertEqual({d["command_id"] for d in desks}, {7})
        self.assertTrue(all(d["dispatch_intent_at"] is not None for d in desks))
        self.assertEqual({d["last_position_mm"] for d in desks}, {1000})

    def test_dispatch_intent_is_saved_before_each_command(self):
        run_to_dispatch(self.service, self.clock, self.spawn)
        for desk_id in ("desk-a", "desk-b"):
            self.assertLess(self.store.log.index(("intent", desk_id)), self.store.log.index(("send", desk_id)))

    def test_no_command_is_sent_when_the_intent_cannot_be_saved(self):
        self.store.fail_intent = True
        operation_id = run_to_dispatch(self.service, self.clock, self.spawn)

        self.workflow.request_height.assert_not_called()
        view = self.service.get(operation_id)
        self.assertEqual(view.state, BLOCKED)
        self.assertEqual({d.result for d in view.desks}, {"not_sent"})
        self.assertEqual(self.store.operations[operation_id]["state"], BLOCKED)

    def test_nothing_is_created_when_the_operation_cannot_be_saved(self):
        self.store.fail_save = True
        with self.assertRaises(GroupOperationError) as error:
            self.service.create(["desk-a"], 1000)
        self.assertEqual(error.exception.reason, "unavailable")
        self.store.fail_save = False
        self.service.create(["desk-a"], 1000)  # the reservation was released

    def test_results_and_history_remain_after_restart(self):
        operation_id = run_to_dispatch(self.service, self.clock, self.spawn)
        before = self.service.get(operation_id)

        restarted, _, _ = make_service(self.store, make_workflow([]))
        after = restarted.get(operation_id)
        self.assertEqual(after.state, before.state)
        self.assertEqual([(d.desk_id, d.result, d.move.command_id) for d in after.desks],
                         [(d.desk_id, d.result, d.move.command_id) for d in before.desks])
        self.assertFalse(after.cancellable)

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_group_service] = lambda: restarted
        with TestClient(app) as client:
            detail = client.get(f"/api/group-operations/{operation_id}")
            self.assertEqual(detail.status_code, 200)
            self.assertEqual(detail.json()["desks"][0]["command_status"], "accepted")
            page = client.get("/api/group-operations/history", params={"limit": 1}).json()
            self.assertEqual([op["operation_id"] for op in page["operations"]], [operation_id])
            self.assertEqual(client.get("/api/group-operations/history", params={"limit": 101}).status_code, 422)

    def test_creation_is_blocked_until_recovery_succeeds(self):
        service, _, spawn = make_service(
            self.store, self.workflow, recover=False,
        )
        self.store.mark_interrupted_operations = Mock(
            side_effect=DatabaseError("database unavailable")
        )

        with self.assertRaises(DatabaseError):
            service.recover_interrupted()

        with self.assertRaises(GroupOperationError) as error:
            service.create(["desk-a"], 1000)

        self.assertEqual(error.exception.reason, "unavailable")
        self.assertEqual(self.store.operations, {})
        self.workflow.request_height.assert_not_called()
        spawn.assert_not_called()

    def test_failed_final_save_does_not_report_success(self):
        original_save = self.store.save_operation

        def save_operation(operation, desks=()):
            if operation["state"] == COMPLETED:
                raise DatabaseError("final save failed")
            return original_save(operation, desks)

        self.store.save_operation = save_operation

        operation_id = run_to_dispatch(
            self.service, self.clock, self.spawn,
        )
        view = self.service.get(operation_id)

        self.assertEqual(view.state, "interrupted")
        self.assertEqual(view.review_state, "needs_review")
        self.assertEqual(view.blocked_code, "storage_unavailable")
        self.assertNotEqual(self.store.operations[operation_id]["state"], COMPLETED)

        with self.assertRaises(GroupOperationError) as error:
            self.service.create(["desk-a"], 1000)

        self.assertEqual(error.exception.reason, "unavailable")


# ---------- PostgreSQL ----------

@pytest.fixture
def db(postgres_test_db, query_test_db):
    return query_test_db


def _saved_command(desk_id):
    from DeskSystemPROJECT.Data import desk_command_repository
    desk_command_repository.save_desk_identity(at_target_record(desk_id))
    return desk_command_repository.save_command(desk_id, 1000, "accepted")


def test_postgres_operation_survives_restart_and_paginates(db):
    from DeskSystemPROJECT.Data import group_operation_repository as store

    command_id = _saved_command("desk-a")
    log = []
    service, clock, spawn = make_service(store, make_workflow(log, command_id))
    first = run_to_dispatch(service, clock, spawn, desks=("desk-a",))
    cancelled = service.create(["desk-a"], 900)
    service.cancel(cancelled.operation_id)

    restarted, _, _ = make_service(store, make_workflow([]))
    view = restarted.get(first)
    assert view.state == COMPLETED
    assert view.desks[0].result == "reached"
    assert view.desks[0].move.command_id == command_id
    assert view.desks[0].dispatch_intent_at is not None
    assert restarted.get(cancelled.operation_id).desks[0].result == "cancelled"
    assert len(restarted.history(limit=1)) == 1
    assert {op.operation_id for op in restarted.history(limit=10)} == {first, cancelled.operation_id}
    assert db("SELECT count(*) FROM group_operation_desks")[0][0] == 2


def test_postgres_incident_deduplicates_and_reopens_after_recovery(db):
    from DeskSystemPROJECT.Data import desk_repository

    def reading(**state):
        record = sample_desk()  # carries historical lastErrors in every reading
        record["state"].update(state)
        return desk_repository.save_desk(record)

    reading()  # healthy, with old lastErrors: not an incident
    assert db("SELECT count(*) FROM desk_incidents")[0][0] == 0

    reading(isAntiCollision=True)
    reading(isAntiCollision=True)
    reading(isAntiCollision=True, status="unknown")  # uncertain: not proof of recovery
    rows = db("SELECT fault_category, observation_count, cleared_at FROM desk_incidents")
    assert rows == [("collision", 3, None)]

    reading()  # recovered
    reading(isAntiCollision=True)  # a new occurrence
    rows = db("SELECT observation_count, cleared_at IS NULL FROM desk_incidents ORDER BY incident_id")
    assert rows == [(3, False), (1, True)]


def test_postgres_startup_recovery_marks_interrupted_without_resending(db):
    from DeskSystemPROJECT.Data import group_operation_repository as store
    from DeskSystemPROJECT.Data import desk_repository

    command_id = _saved_command("desk-a")
    now = datetime.now(timezone.utc)
    store.save_operation(
        {"operation_id": "op-1", "reason": "test", "target_position_mm": 1000, "state": "monitoring",
         "required_channels": ["dashboard"], "created_at": now, "dispatched_at": now, "finished_at": None,
         "blocked_code": None, "blocked_message": None, "review_state": "not_required"},
        [{"desk_id": desk_id, "result": result, "detail": "x", "command_id": cid,
          "command_status": "accepted" if cid else None, "accepted_position_mm": None,
          "last_position_mm": None, "last_speed_mms": None, "last_status": None,
          "last_observed_at": None, "fault_codes": [], "at_target": None}
         for desk_id, result, cid in (("desk-a", "reached", command_id), ("desk-b", "moving", None),
                                      ("desk-c", "pending", None), ("desk-d", "pending", None))],
    )
    store.record_dispatch_intent("op-1", "desk-c")  # sent? unknown: the crash came first

    def collision(desk_id):
        record = at_target_record(desk_id)
        record["state"]["isAntiCollision"] = True
        desk_repository.save_desk(record)

    collision("desk-b")  # while op-1 is still active, the incident is linked to it

    workflow = make_workflow([])
    service, clock, spawn = make_service(store, workflow, recover=False)
    assert service.recover_interrupted() == ["op-1"]
    clock.now = 100
    service.tick()

    view = service.get("op-1")
    assert view.state == "interrupted" and view.review_state == "needs_review"
    assert {d.desk_id: d.result for d in view.desks} == {
        "desk-a": "reached", "desk-b": "unverified", "desk-c": "unknown", "desk-d": "not_sent",
    }
    workflow.request_height.assert_not_called()
    spawn.assert_not_called()
    assert service.recover_interrupted() == []  # nothing left to recover

    # after recovery op-1 is no longer active, so a new incident has no operation
    collision("desk-e")
    assert db("SELECT desk_id, operation_id FROM desk_incidents ORDER BY incident_id") == [
        ("desk-b", "op-1"), ("desk-e", None),
    ]
