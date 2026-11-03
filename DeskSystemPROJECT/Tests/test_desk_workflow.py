# Checks show, sync, and move, including what happens when one step fails.
# API, storage, and waiting are replaced with mocks to check results and call order.

import contextlib
import io
import unittest
from unittest.mock import Mock

from DeskSystemPROJECT.Data.database import DatabaseError
from DeskSystemPROJECT.Data.desk_api_client import DeskAPIError
from DeskSystemPROJECT.Domain.desk_workflow import DeskWorkflow, WorkflowError
from DeskSystemPROJECT.Tests.fixtures import sample_desk
from DeskSystemPROJECT.UI.cli import main


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        # Replace external calls and waiting so each test controls the whole workflow.
        self.api, self.readings, self.commands, self.sleep = Mock(), Mock(), Mock(), Mock()
        self.connect = Mock()
        self.record = sample_desk()
        self.api.get_desk.return_value = self.record
        self.api.get_desk_ids.return_value = [self.record["desk_id"]]
        self.api.set_desk_height.return_value = {"position_mm": 1320}
        self.readings.save_desk.return_value = 7
        self.commands.desk_exists.return_value = True
        self.commands.save_command.return_value = 8
        self.workflow = DeskWorkflow(
            "http://127.0.0.1:8000", "key", self.api, self.readings, self.commands,
            self.sleep, connect=self.connect,
        )

    def test_show_does_not_touch_database_and_keeps_partial_results(self):
        self.api.get_desk_ids.return_value = ["first", "second"]
        self.api.get_desk.side_effect = [self.record, DeskAPIError("offline")]
        result = self.workflow.fetch_all()
        self.assertEqual(result[0].record, self.record)
        self.assertEqual(result[1].error, "offline")
        self.assertEqual(self.readings.mock_calls, [])
        self.assertEqual(self.commands.mock_calls, [])
        self.connect.assert_not_called()

    def test_sync_continues_after_a_failed_desk(self):
        self.api.get_desk_ids.return_value = ["first", "second"]
        self.api.get_desk.side_effect = [DeskAPIError("offline"), self.record]
        report = self.workflow.sync_all()
        self.assertEqual((report.saved, report.failed), (1, 1))
        self.readings.save_desk.assert_called_once_with(self.record)

    def test_accepted_move_records_requested_height_then_reads(self):
        result = self.workflow.request_height("desk-1", 2000, wait_s=2)
        self.assertTrue(result.succeeded)
        self.assertEqual(result.accepted_mm, 1320)
        self.commands.save_command.assert_called_once_with("desk-1", 2000, "accepted")
        self.sleep.assert_called_once_with(2)
        self.readings.save_desk.assert_called_once_with(self.record)

    def test_failed_move_is_recorded_without_followup(self):
        self.api.set_desk_height.side_effect = DeskAPIError("offline")
        result = self.workflow.request_height("desk-1", 900)
        self.assertFalse(result.succeeded)
        self.commands.save_command.assert_called_once_with("desk-1", 900, "failed")
        self.readings.save_desk.assert_not_called()

    def test_unavailable_database_prevents_movement(self):
        self.connect.side_effect = DatabaseError("offline")
        with self.assertRaisesRegex(WorkflowError, "Nothing was sent"):
            self.workflow.request_height("desk-1", 900)
        self.api.set_desk_height.assert_not_called()
        self.commands.save_command.assert_not_called()

    def test_new_desk_identity_is_saved_before_movement(self):
        self.commands.desk_exists.return_value = False
        # Collect calls from both mocks to check that identity is saved before moving.
        calls = Mock()
        calls.attach_mock(self.commands.save_desk_identity, "identity")
        calls.attach_mock(self.api.set_desk_height, "move")
        self.workflow.request_height("desk-1", 900)
        self.assertEqual([call[0] for call in calls.mock_calls], ["identity", "move"])

    def test_recording_failure_does_not_hide_accepted_movement(self):
        self.commands.save_command.side_effect = DatabaseError("write failed")
        result = self.workflow.request_height("desk-1", 900)
        self.assertEqual(result.status, "accepted")
        self.assertEqual(result.record_error, "write failed")
        self.assertFalse(result.succeeded)
        self.readings.save_desk.assert_called_once()

    def test_cli_with_no_command_only_prints_help(self):
        factory = Mock()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([], env={}, workflow_factory=factory), 0)
        factory.assert_not_called()

    def test_cli_passes_configuration_and_keeps_show_exit_code(self):
        factory = Mock(return_value=self.workflow)
        with contextlib.redirect_stdout(io.StringIO()):
            code = main(["show"], env={"DESK_API_KEY": "key"}, workflow_factory=factory)
        self.assertEqual(code, 0)
        factory.assert_called_once_with("http://127.0.0.1:8000", "key")
