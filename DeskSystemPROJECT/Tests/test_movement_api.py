"""Exercise HTTP validation through the real workflow with fake infrastructure."""

import contextlib
import io
import os
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from DeskSystemPROJECT.Data.database import DatabaseError
from DeskSystemPROJECT.Data.desk_api_client import DeskAPIError
from DeskSystemPROJECT.Domain.desk_workflow import DeskWorkflow
from DeskSystemPROJECT.server import app, get_movement_workflow
from DeskSystemPROJECT.Tests.fixtures import sample_desk
from DeskSystemPROJECT.UI.cli import main


class MovementAPITests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {"DATABASE_URL": ""}))
        self.api, self.readings, self.commands, self.connect = Mock(), Mock(), Mock(), Mock()
        self.api.get_desk.return_value = sample_desk()
        self.api.set_desk_height.return_value = {"position_mm": 950}
        self.readings.save_desk.return_value = 7
        self.commands.desk_exists.return_value = True
        self.commands.save_command.return_value = 8
        self.workflow = DeskWorkflow(
            "http://simulator.test", "key", self.api, self.readings,
            self.commands, connect=self.connect,
        )
        self.enterContext(patch.dict(app.dependency_overrides, {get_movement_workflow: lambda: self.workflow}))
        self.client = self.enterContext(TestClient(app))

    def post(self, payload=None, desk_id="desk-1"):
        return self.client.post(
            f"/api/desks/{desk_id}/height",
            json={"target_position_mm": 1000} if payload is None else payload,
        )

    def test_accepted_adjusted_target_is_recorded_with_follow_up(self):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "desk_id": "desk-1", "requested_position_mm": 1000,
            "accepted_position_mm": 950, "command_id": 8,
            "status": "accepted", "error": None, "recording_error": None,
            "follow_up_error": None, "reading_id": 7,
        })
        self.api.set_desk_height.assert_called_once_with("http://simulator.test", "key", "desk-1", 1000)
        self.commands.save_command.assert_called_once_with("desk-1", 1000, "accepted")
        self.assertEqual(self.api.get_desk.call_count, 2)

    def test_strict_height_and_identifier_validation_prevents_any_io(self):
        for value in (True, False, "1000", 1000.0, None, 679, 1321, -1):
            with self.subTest(value=value):
                self.assertEqual(self.post({"target_position_mm": value}).status_code, 422)
        self.assertEqual(self.post({}).status_code, 422)
        self.assertEqual(self.post({"target_position_mm": 1000, "extra": 1}).status_code, 422)
        for desk_id in ("%20", "bad%20id", "bad%3Fid", "a" * 129):
            self.assertEqual(self.post(desk_id=desk_id).status_code, 422)
        self.assertEqual(self.api.mock_calls, [])
        self.connect.assert_not_called()
        self.commands.save_command.assert_not_called()

    def test_range_boundaries_are_allowed(self):
        for height in (680, 1320):
            self.assertEqual(self.post({"target_position_mm": height}).json()["status"], "accepted")

    def test_preflight_errors_are_safe_and_prevent_movement(self):
        cases = (
            (self.api.validate_config, DeskAPIError("private-key"), 503),
            (self.connect, DatabaseError("password=private-key"), 503),
            (self.api.get_desk, DeskAPIError("private-key", 404), 404),
            (self.api.get_desk, DeskAPIError("private-key"), 502),
            (self.commands.desk_exists, DatabaseError("private-key"), 503),
        )
        for dependency, error, status in cases:
            with self.subTest(status=status):
                dependency.side_effect = error
                response = self.post()
                self.assertEqual(response.status_code, status)
                self.assertNotIn("private-key", response.text)
                self.assertIn("Nothing was sent", response.text)
                dependency.side_effect = None
        self.api.set_desk_height.assert_not_called()

    def test_rejection_is_recorded_without_follow_up(self):
        self.api.set_desk_height.side_effect = DeskAPIError("private-key", 400)
        response = self.post()
        self.assertEqual(response.json()["status"], "failed")
        self.commands.save_command.assert_called_once_with("desk-1", 1000, "failed")
        self.readings.save_desk.assert_not_called()
        self.assertNotIn("private-key", response.text)

    def test_uncertain_commands_are_never_retried(self):
        for error in (DeskAPIError("timeout"), DeskAPIError("server error", 500)):
            with self.subTest(error=str(error)):
                self.api.set_desk_height.reset_mock()
                self.api.set_desk_height.side_effect = error
                response = self.post()
                self.assertEqual(response.json()["status"], "unknown")
                self.assertIsNone(response.json()["accepted_position_mm"])
                self.api.set_desk_height.assert_called_once()
                self.commands.save_command.assert_called_with("desk-1", 1000, "unknown")
        self.readings.save_desk.assert_not_called()

    def test_invalid_acknowledgement_is_unknown(self):
        for acknowledgement in ({}, {"position_mm": True}, {"position_mm": "1000"}):
            self.api.set_desk_height.return_value = acknowledgement
            self.assertEqual(self.post().json()["status"], "unknown")

    def test_partial_failures_preserve_acceptance_and_hide_details(self):
        self.commands.save_command.side_effect = DatabaseError("password=private-key")
        self.readings.save_desk.side_effect = DatabaseError("password=private-key")
        response = self.post()
        data = response.json()
        self.assertEqual(data["status"], "accepted")
        self.assertEqual(data["accepted_position_mm"], 950)
        self.assertIsNone(data["command_id"])
        self.assertIsNone(data["reading_id"])
        self.assertTrue(data["recording_error"])
        self.assertTrue(data["follow_up_error"])
        self.assertNotIn("private-key", response.text)
        self.api.set_desk_height.assert_called_once()

    def test_follow_up_fetch_failure_keeps_recorded_command(self):
        self.api.get_desk.side_effect = [sample_desk(), DeskAPIError("private-key")]
        response = self.post()
        self.assertEqual(response.json()["status"], "accepted")
        self.assertEqual(response.json()["command_id"], 8)
        self.assertTrue(response.json()["follow_up_error"])
        self.assertNotIn("private-key", response.text)

    def test_cli_reports_uncertainty_and_uses_shared_range_validation(self):
        self.api.set_desk_height.side_effect = DeskAPIError("timeout")
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = main(["move", "desk-1", "1000", "--wait", "0"],
                        env={"DESK_API_KEY": "key"}, workflow_factory=lambda *args: self.workflow)
        self.assertEqual(code, 1)
        self.assertIn("Request UNKNOWN", output.getvalue())
        self.assertIn("may have moved", output.getvalue())
        self.api.set_desk_height.reset_mock()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = main(["move", "desk-1", "2000"], env={"DESK_API_KEY": "key"},
                        workflow_factory=lambda *args: self.workflow)
        self.assertEqual(code, 1)
        self.api.set_desk_height.assert_not_called()
