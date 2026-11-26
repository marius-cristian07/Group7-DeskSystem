"""
Edited by : Edris Fiazi
Edited on : 26.11.2026
Purpose   : KAN-36 Test Pico warning failures, cancellation, and collision handling for group moves.

S5-6 integration checks for the group warning and movement workflow.

These tests use a fake simulator/database boundary and an injected clock. They do
not move physical desks or require PostgreSQL, a running simulator, or a Pico.
"""

import unittest
from unittest.mock import Mock, call, patch

import serial

from DeskSystemPROJECT.Domain.group_operations import (
    BLOCKED,
    CANCELLED,
    COUNTDOWN,
    DISPATCHING,
    GroupOperationError,
    GroupOperationService,
    GroupOperationSettings,
    DeskBusyError,
)

from DeskSystemPROJECT.server import warn_before_movement


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class GroupOperationIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.workflow = Mock()
        self.workflow.api.get_desk.return_value = {"state": {"status": "Normal"}}
        self.workflow.connect.return_value.close = Mock()
        self.spawn = Mock()
        self.settings = GroupOperationSettings(
            countdown_s=10,
            ack_timeout_s=15,
            stale_s=15,
            required_channels=("pico", "dashboard"),
            monitor_timeout_s=2,
            monitor_poll_s=0.1,
        )
        self.service = GroupOperationService(
            lambda: self.workflow,
            settings=self.settings,
            clock=self.clock,
            wall_clock=lambda: 1_800_000_000,
            sleep=Mock(),
            spawn=self.spawn,
        )

    def create(self, desks=("desk-a",)):
        return self.service.create(list(desks), 1000)

    def acknowledge_both(self, operation_id):
        self.service.acknowledge(operation_id, "pico")
        return self.service.acknowledge(operation_id, "dashboard")

    def test_no_dispatch_until_both_channels_acknowledge_and_countdown_finishes(self):
        operation = self.create()

        self.service.acknowledge(operation.operation_id, "dashboard")
        self.assertEqual(self.service.get(operation.operation_id).state, "pending_warning")
        self.spawn.assert_not_called()

        self.service.acknowledge(operation.operation_id, "pico")
        self.assertEqual(self.service.get(operation.operation_id).state, COUNTDOWN)
        self.clock.now = 9.9
        self.service.tick()
        self.spawn.assert_not_called()

        self.clock.now = 10
        self.service.tick()
        # The Pico must provide its final button/clear result after the deadline.
        self.assertEqual(self.service.get(operation.operation_id).state, COUNTDOWN)
        self.service.finish_pico_warning(operation.operation_id)
        self.assertEqual(self.service.get(operation.operation_id).state, DISPATCHING)
        self.spawn.assert_called_once()

    def test_cancel_during_warning_prevents_dispatch_and_releases_desk(self):
        operation = self.create()
        result = self.service.cancel(operation.operation_id)

        self.assertEqual(result.state, CANCELLED)
        self.assertEqual(result.desks[0].result, "cancelled")
        self.assertFalse(result.cancellable)
        self.spawn.assert_not_called()

        # A cancelled operation no longer reserves its desks.
        second = self.create()
        self.assertEqual(second.state, "pending_warning")

    def test_missing_warning_acknowledgement_blocks_without_dispatch(self):
        operation = self.create()
        self.clock.now = 15
        self.service.tick()

        result = self.service.get(operation.operation_id)
        self.assertEqual(result.state, BLOCKED)
        self.assertEqual(result.blocked_code, "warning_not_acknowledged")
        self.assertEqual(result.desks[0].result, "not_sent")
        self.spawn.assert_not_called()

    def test_stale_warning_acknowledgement_blocks_without_dispatch(self):
        operation = self.create()
        self.acknowledge_both(operation.operation_id)
        self.clock.now = 26  # countdown ended at 10; last acknowledgement is 26 seconds old
        self.service.tick()

        result = self.service.get(operation.operation_id)
        self.assertEqual(result.state, BLOCKED)
        self.assertEqual(result.blocked_code, "warning_stale")
        self.spawn.assert_not_called()

    def test_cancellation_after_dispatch_boundary_is_refused(self):
        operation = self.create()
        self.acknowledge_both(operation.operation_id)
        self.clock.now = 10
        self.service.finish_pico_warning(operation.operation_id)

        with self.assertRaises(GroupOperationError) as error:
            self.service.cancel(operation.operation_id)
        self.assertEqual(error.exception.reason, "too_late")
        self.assertEqual(self.service.get(operation.operation_id).state, DISPATCHING)
        self.spawn.assert_called_once()

    def test_overlapping_group_and_single_desk_requests_are_rejected(self):
        self.create()
        with self.assertRaises(DeskBusyError):
            self.create()

        with self.assertRaises(DeskBusyError):
            with self.service.reserve_single("desk-a"):
                pass

    def test_preflight_fault_prevents_warning_and_releases_reservation(self):
        self.workflow.api.get_desk.return_value = {
            "state": {"status": "Error", "isAntiCollision": False}
        }
        with self.assertRaises(GroupOperationError) as error:
            self.create()
        self.assertEqual(error.exception.reason, "desks_not_ready")
        self.spawn.assert_not_called()

        # A failed preflight must not leave a desk permanently reserved.
        self.workflow.api.get_desk.return_value = {"state": {"status": "Normal"}}
        self.assertEqual(self.create().state, "pending_warning")

    def test_successful_group_dispatch_is_monitored_until_every_desk_reaches_target(self):
        from DeskSystemPROJECT.Domain.desk_workflow import MoveResult

        operation = self.create(("desk-a", "desk-b"))
        self.acknowledge_both(operation.operation_id)
        self.clock.now = 10
        self.service.finish_pico_warning(operation.operation_id)

        self.workflow.request_height.side_effect = [
            MoveResult("desk-a", 1000, "accepted", accepted_mm=1000, command_id=11),
            MoveResult("desk-b", 1000, "accepted", accepted_mm=1000, command_id=12),
        ]
        self.workflow.api.get_desk.return_value = {
            "state": {"status": "Normal", "position_mm": 1000, "speed_mms": 0}
        }
        # The injected spawn callback is run synchronously to keep the test deterministic.
        worker, operation_id = self.spawn.call_args.args
        worker(operation_id)

        result = self.service.get(operation.operation_id)
        self.assertEqual(result.state, "completed")
        self.assertEqual([desk.result for desk in result.desks], ["reached", "reached"])
        self.assertEqual(self.workflow.request_height.call_count, 2)

    def create_automatic_with_dashboard_ack(self):
        # Even a dashboard-only configuration must require the Pico for automatic moves.
        self.service.settings = GroupOperationSettings(required_channels=("dashboard",))
        operation = self.service.create(["desk-a"], 1000, automatic=True)
        self.service.acknowledge(operation.operation_id, "dashboard")
        return operation.operation_id

    def test_automatic_move_is_blocked_when_pico_never_acknowledges(self):
        operation_id = self.create_automatic_with_dashboard_ack()
        self.clock.now = self.service.settings.ack_timeout_s
        self.service.tick()

        result = self.service.get(operation_id)
        self.assertEqual(result.state, BLOCKED)
        self.assertEqual(result.blocked_code, "warning_not_acknowledged")
        self.assertEqual(result.desks[0].result, "not_sent")
        self.spawn.assert_not_called()
        self.workflow.request_height.assert_not_called()

    def test_automatic_move_is_cancelled_if_usb_disconnects_during_warning(self):
        operation_id = self.create_automatic_with_dashboard_ack()
        port = Mock()
        port.read_until.side_effect = [
            f"ACTIVE {operation_id}\n".encode("ascii"),
            serial.SerialException("USB disconnected"),
        ]
        stop_event = Mock()
        stop_event.is_set.return_value = False

        with self.assertRaises(serial.SerialException):
            warn_before_movement(port, self.service, operation_id, stop_event)

        port.write.assert_has_calls([
            call(f"START {operation_id}\n".encode("ascii")),
            call(f"POLL {operation_id}\n".encode("ascii")),
        ])
        self.assertEqual(self.service.get(operation_id).state, CANCELLED)
        self.spawn.assert_not_called()
        self.workflow.request_height.assert_not_called()

    def test_automatic_move_requires_clear_for_the_same_operation(self):
        operation_id = self.create_automatic_with_dashboard_ack()
        port = Mock()
        port.read_until.side_effect = [
            f"ACTIVE {operation_id}\n".encode("ascii"),
            b"CLEAR another-operation\n",
        ]
        stop_event = Mock()
        stop_event.is_set.return_value = False

        def finish_countdown(_seconds):
            self.clock.now = self.service.settings.countdown_s

        stop_event.wait.side_effect = finish_countdown

        # Let START receive ACTIVE, then let FINISH time out after the unrelated CLEAR.
        with patch("DeskSystemPROJECT.server.time") as serial_time:
            serial_time.monotonic.side_effect = [0, 0, 0, 0, 1]
            with self.assertRaisesRegex(serial.SerialException, "No reply"):
                warn_before_movement(port, self.service, operation_id, stop_event)

        port.write.assert_has_calls([
            call(f"START {operation_id}\n".encode("ascii")),
            call(f"FINISH {operation_id}\n".encode("ascii")),
        ])
        self.assertEqual(self.service.get(operation_id).state, CANCELLED)
        self.spawn.assert_not_called()
        self.workflow.request_height.assert_not_called()

    def test_automatic_move_handles_pico_button_and_clear_after_countdown(self):
        for reply, expected_state in (("CANCEL", CANCELLED), ("CLEAR", DISPATCHING)):
            with self.subTest(reply=reply):
                self.spawn.reset_mock()
                operation_id = self.create_automatic_with_dashboard_ack()
                port = Mock()
                port.read_until.side_effect = [
                    f"ACTIVE {operation_id}\n".encode("ascii"),
                    f"{reply} {operation_id}\n".encode("ascii"),
                ]
                stop_event = Mock()
                stop_event.is_set.return_value = False

                def finish_countdown(_seconds):
                    self.clock.now += self.service.settings.countdown_s

                stop_event.wait.side_effect = finish_countdown
                warn_before_movement(port, self.service, operation_id, stop_event)

                port.write.assert_called_with(f"FINISH {operation_id}\n".encode("ascii"))
                self.assertEqual(self.service.get(operation_id).state, expected_state)
                if reply == "CLEAR":
                    self.spawn.assert_called_once()
                else:
                    self.spawn.assert_not_called()
                    self.workflow.request_height.assert_not_called()

    def test_group_move_reports_collision_even_at_target_height(self):
        from DeskSystemPROJECT.Domain.desk_workflow import MoveResult

        operation = self.create()
        self.acknowledge_both(operation.operation_id)
        self.clock.now = 10
        self.service.finish_pico_warning(operation.operation_id)

        self.workflow.request_height.return_value = MoveResult(
            "desk-a", 1000, "accepted", accepted_mm=1000, command_id=11,
        )
        self.workflow.api.get_desk.side_effect = [
            {"state": {"status": "Normal"}},
            {"state": {
                "status": "Normal", "position_mm": 1000, "speed_mms": 0,
                "isAntiCollision": True,
            }},
        ]
        worker, operation_id = self.spawn.call_args.args
        worker(operation_id)

        self.workflow.request_height.assert_called_once_with("desk-a", 1000)
        result = self.service.get(operation_id)
        self.assertEqual(result.state, "failed")
        self.assertEqual(result.desks[0].result, "desk_error")
        self.assertTrue(result.desks[0].at_target)
        self.assertIn("collision", result.desks[0].fault_codes)

    def test_partial_failure_is_reported_per_desk(self):
        from DeskSystemPROJECT.Domain.desk_workflow import MoveResult

        operation = self.create(("desk-a", "desk-b"))
        self.acknowledge_both(operation.operation_id)
        self.clock.now = 10
        self.service.finish_pico_warning(operation.operation_id)

        def send(desk_id, target):
            if desk_id == "desk-a":
                return MoveResult(desk_id, target, "accepted", accepted_mm=target, command_id=21)
            return MoveResult(desk_id, target, "failed", command_id=22)

        self.workflow.request_height.side_effect = send
        self.workflow.api.get_desk.return_value = {
            "state": {"status": "Normal", "position_mm": 1000, "speed_mms": 0}
        }
        worker, operation_id = self.spawn.call_args.args
        worker(operation_id)

        result = self.service.get(operation.operation_id)
        self.assertEqual(result.state, "partial_failure")
        self.assertEqual([desk.result for desk in result.desks], ["reached", "rejected"])
        self.assertEqual(self.workflow.request_height.call_count, 2)

    def test_uncertain_send_is_marked_unknown_and_never_retried(self):
        from DeskSystemPROJECT.Domain.group_operations import _Desk

        desk = _Desk("desk-a")
        GroupOperationService._record_send(desk, None, "unexpected")
        self.assertEqual(desk.result, "unknown")
        self.assertIn("not retried", desk.detail)
        self.assertIsNone(desk.move)


if __name__ == "__main__":
    unittest.main()
