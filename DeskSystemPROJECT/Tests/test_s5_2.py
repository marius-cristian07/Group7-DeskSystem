"""S5-2 offline tests. No database or simulator connections are made."""

import unittest
from datetime import date, datetime, time, timezone
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from DeskSystemPROJECT.Domain.cleaning_schedule_timing import get_window_utc
from DeskSystemPROJECT.Domain.cleaning_schedule_validation import schedules_overlap
from DeskSystemPROJECT.Domain.cleaning_scheduler import CleaningScheduler
from DeskSystemPROJECT.Domain.group_operations import GroupOperationError
from DeskSystemPROJECT.Data.cleaning_schedule_repository import ScheduleBusyError, ScheduleConflictError
from DeskSystemPROJECT.cleaning_schedules_api import router
from DeskSystemPROJECT.group_operations_api import get_group_service


class TimingTests(unittest.TestCase):
    def test_overnight_and_dst(self):
        schedule = {"timezone": "Europe/Copenhagen", "start_time": time(22), "end_time": time(6)}
        start, end = get_window_utc(schedule, date(2026, 11, 17))
        self.assertEqual(start, datetime(2026, 11, 17, 21, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2026, 11, 18, 5, tzinfo=timezone.utc))
        schedule.update(start_time=time(2, 30), end_time=time(4))
        with self.assertRaises(ValueError):
            get_window_utc(schedule, date(2026, 3, 29))

    def test_overlap(self):
        self.assertTrue(schedules_overlap(time(22), time(6), time(23), time(2)))
        self.assertTrue(schedules_overlap(time(22), time(6), time(5), time(7)))
        self.assertFalse(schedules_overlap(time(22), time(6), time(6), time(8)))
        self.assertFalse(schedules_overlap(time(10), time(12), time(13), time(15)))


class SchedulerTests(unittest.TestCase):
    def test_due_actions_disabled_return(self):
        schedule = {"schedule_id": 10, "is_enabled": False, "timezone": "Europe/Copenhagen",
                    "start_time": time(22), "end_time": time(6)}
        with patch("DeskSystemPROJECT.Domain.cleaning_scheduler.repository.list_schedules", return_value=[schedule]):
            scheduler = CleaningScheduler()
            self.assertEqual(scheduler.get_due_actions(
                datetime(2026, 11, 17, 21, tzinfo=timezone.utc)), [])
            self.assertEqual(scheduler.get_due_actions(
                datetime(2026, 11, 18, 5, tzinfo=timezone.utc)),
                [("return", 10, date(2026, 11, 17))])

    def test_tick_calls_s5_1_twice(self):
        scheduler = CleaningScheduler()
        service = Mock()
        service.create.side_effect = [SimpleNamespace(operation_id="up"),
                                      SimpleNamespace(operation_id="down")]
        schedule = {"schedule_id": 10, "is_enabled": True,
                    "desk_ids": ["desk-a"], "cleaning_height_mm": 1200,
                    "return_height_mm": 720, "timezone": "Europe/Copenhagen",
                    "start_time": time(22), "end_time": time(6)}
        day = date(2026, 11, 17)
        with (patch.object(scheduler, "check_operations"),
              patch.object(scheduler, "mark_overdue"),
              patch.object(scheduler, "mark_missed_starts"),
              patch.object(scheduler, "get_due_actions") as due,
              patch("DeskSystemPROJECT.Domain.cleaning_scheduler.repository.get_schedule", return_value=schedule),
              patch("DeskSystemPROJECT.Domain.cleaning_scheduler.repository.claim_cleaning_start", return_value=101) as start,
              patch("DeskSystemPROJECT.Domain.cleaning_scheduler.repository.claim_cleaning_return", return_value=101),
              patch("DeskSystemPROJECT.Domain.cleaning_scheduler.repository.save_raise_operation", return_value=True) as save_up,
              patch("DeskSystemPROJECT.Domain.cleaning_scheduler.repository.save_return_operation", return_value=True) as save_down):
            due.return_value = [("start", 10, day)]
            scheduler.tick(service, datetime(2026, 11, 17, 21, tzinfo=timezone.utc))
            due.return_value = [("return", 10, day)]
            scheduler.tick(service, datetime(2026, 11, 18, 5, tzinfo=timezone.utc))
            self.assertEqual(service.create.call_args_list,
                             [call(["desk-a"], 1200, reason="Scheduled cleaning: raise desks", automatic=True),
                              call(["desk-a"], 720, reason="Scheduled cleaning: return desks", automatic=True)])
            start.assert_called_once_with(10, day, datetime(2026, 11, 17, 21, tzinfo=timezone.utc))
            save_up.assert_called_once_with(101, "up")
            save_down.assert_called_once_with(101, "down")

    def test_states_and_missing_operation(self):
        runs = [
            {"run_id": 1, "status": "raising", "raise_operation_id": "ok", "return_operation_id": None},
            {"run_id": 2, "status": "raising", "raise_operation_id": "cancel", "return_operation_id": None},
            {"run_id": 3, "status": "returning", "raise_operation_id": "ok", "return_operation_id": "done"},
            {"run_id": 4, "status": "raising", "raise_operation_id": None, "return_operation_id": None},
        ]
        service = Mock()
        states = {"ok": "completed", "cancel": "cancelled", "done": "completed"}
        service.get.side_effect = lambda ident: SimpleNamespace(state=states[ident])
        with (patch("DeskSystemPROJECT.Domain.cleaning_scheduler.repository.get_active_movement_runs", return_value=runs),
              patch("DeskSystemPROJECT.Domain.cleaning_scheduler.repository.set_run_status") as change):
            CleaningScheduler().check_operations(service)
            self.assertEqual(change.call_args_list, [
                call(1, "raising", "cleaning"), call(2, "raising", "cancelled"),
                call(3, "returning", "completed"), call(4, "raising", "needs_review")])

    def test_missed_start_is_recorded_for_review(self):
        schedule = {"schedule_id": 10, "is_enabled": True,
                    "timezone": "Europe/Copenhagen", "start_time": time(22), "end_time": time(6)}
        now = datetime(2026, 11, 18, 5, 2, tzinfo=timezone.utc)
        with (patch("DeskSystemPROJECT.Domain.cleaning_scheduler.repository.list_schedules", return_value=[schedule]),
              patch("DeskSystemPROJECT.Domain.cleaning_scheduler.repository.claim_missed_start") as record):
            CleaningScheduler().mark_missed_starts(now)
            record.assert_called_once_with(
                10, date(2026, 11, 17),
                datetime(2026, 11, 17, 21, tzinfo=timezone.utc),
            )

    def test_overdue_return_requires_review(self):
        run = {"run_id": 11, "occurrence_date": date(2026, 11, 17),
               "status": "cleaning", "start_time": time(22),
               "end_time": time(6), "timezone": "Europe/Copenhagen"}
        with (patch("DeskSystemPROJECT.Domain.cleaning_scheduler.repository.get_unfinished_runs", return_value=[run]),
              patch("DeskSystemPROJECT.Domain.cleaning_scheduler.repository.set_run_status") as update):
            CleaningScheduler().mark_overdue(datetime(2026, 11, 18, 5, 2, tzinfo=timezone.utc))
            update.assert_called_once_with(11, "cleaning", "needs_review")

    def test_failed_persistence_cancels_warning(self):
        scheduler = CleaningScheduler()
        service = Mock()
        service.create.return_value = SimpleNamespace(operation_id="warn-1")
        schedule = {"schedule_id": 8, "is_enabled": True, "desk_ids": ["desk-a"],
                    "cleaning_height_mm": 1200, "return_height_mm": 720,
                    "timezone": "Europe/Copenhagen", "start_time": time(22), "end_time": time(6)}
        with (patch.object(scheduler, "check_operations"),
              patch.object(scheduler, "mark_overdue"),
              patch.object(scheduler, "mark_missed_starts"),
              patch.object(scheduler, "get_due_actions", return_value=[("start", 8, date(2026, 11, 17))]),
              patch("DeskSystemPROJECT.Domain.cleaning_scheduler.repository.get_schedule", return_value=schedule),
              patch("DeskSystemPROJECT.Domain.cleaning_scheduler.repository.claim_cleaning_start", return_value=17),
              patch("DeskSystemPROJECT.Domain.cleaning_scheduler.repository.save_raise_operation", return_value=False),
              patch("DeskSystemPROJECT.Domain.cleaning_scheduler.repository.set_run_status") as status):
            scheduler.tick(service, datetime(2026, 11, 17, 21, tzinfo=timezone.utc))
            service.cancel.assert_called_once_with("warn-1")
            status.assert_called_once_with(17, "raising", "needs_review")


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(router)
        self.service = Mock()
        self.app.dependency_overrides[get_group_service] = lambda: self.service
        self.client = TestClient(self.app)
        self.data = {"name": "Night cleaning", "cleaning_height_mm": 1200,
                     "return_height_mm": 720, "start_time": "22:00",
                     "end_time": "06:00", "timezone": "Europe/Copenhagen", "desk_ids": ["desk-a"]}

    def tearDown(self):
        self.client.close()
        self.app.dependency_overrides.clear()

    def test_bad_timezone_and_seconds(self):
        self.data["timezone"] = "Banana/Denmark"
        self.assertEqual(self.client.post("/api/cleaning-schedules", json=self.data).status_code, 422)
        self.data["timezone"] = "Europe/Copenhagen"
        self.data["start_time"] = "22:00:30"
        self.assertEqual(self.client.post("/api/cleaning-schedules", json=self.data).status_code, 422)

    def test_conflict_is_409(self):
        with (patch("DeskSystemPROJECT.cleaning_schedules_api.desk_exists", return_value=True),
              patch("DeskSystemPROJECT.cleaning_schedules_api.repository.create_schedule",
                    side_effect=ScheduleConflictError("Conflicts with schedule 1"))):
            response = self.client.post("/api/cleaning-schedules", json=self.data)
            self.assertEqual(response.status_code, 409)

    def test_active_update_is_409(self):
        with (patch("DeskSystemPROJECT.cleaning_schedules_api.desk_exists", return_value=True),
              patch("DeskSystemPROJECT.cleaning_schedules_api.repository.update_schedule",
                    side_effect=ScheduleBusyError("Busy"))):
            response = self.client.put("/api/cleaning-schedules/3", json=self.data)
            self.assertEqual(response.status_code, 409)

    def test_cancel_active_warning(self):
        run = {"run_id": 42, "status": "raising",
               "raise_operation_id": "warn1", "return_operation_id": None}
        self.service.cancel.return_value = SimpleNamespace(state="cancelled")
        with (patch("DeskSystemPROJECT.cleaning_schedules_api.repository.get_cleaning_run", return_value=run),
              patch("DeskSystemPROJECT.cleaning_schedules_api.repository.set_run_status", return_value=True) as change):
            response = self.client.post("/api/cleaning-schedules/runs/42/cancel")
            self.assertEqual(response.status_code, 200)
            self.service.cancel.assert_called_once_with("warn1")
            change.assert_called_once_with(42, "raising", "cancelled")

    def test_cancel_after_dispatch_refused(self):
        run = {"run_id": 42, "status": "raising",
               "raise_operation_id": "warn1", "return_operation_id": None}
        self.service.cancel.side_effect = GroupOperationError("Too late", "too_late")
        with (patch("DeskSystemPROJECT.cleaning_schedules_api.repository.get_cleaning_run", return_value=run),
              patch("DeskSystemPROJECT.cleaning_schedules_api.repository.set_run_status") as change):
            response = self.client.post("/api/cleaning-schedules/runs/42/cancel")
            self.assertEqual(response.status_code, 409)
            change.assert_not_called()


if __name__ == "__main__":
    unittest.main()
