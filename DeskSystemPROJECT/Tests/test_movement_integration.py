"""Optional real simulator HTTP check; PostgreSQL is replaced by test storage."""

import os
from pathlib import Path
import sys
import threading
import unittest
from http.server import HTTPServer
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from DeskSystemPROJECT.Domain.desk_workflow import DeskWorkflow
from DeskSystemPROJECT.server import app, get_movement_workflow


@unittest.skipUnless(os.environ.get("DESK_RUN_MOVEMENT_TESTS") == "1",
                     "Set DESK_RUN_MOVEMENT_TESTS=1 for the isolated simulator check")
class MovementIntegrationTests(unittest.TestCase):
    def test_http_request_moves_one_simulated_desk(self):
        simulator_path = Path(__file__).resolve().parents[2] / "wifi2ble-box-simulator/simulator"
        with patch.object(sys, "path", [str(simulator_path), *sys.path]):
            from desk import Desk
            from desk_manager import DeskManager
            from simple_rest_server import SimpleRESTServer

        # Avoid loading or changing the user's simulator data.
        with patch.object(DeskManager, "load_state"):
            manager = DeskManager(collision_chance=0, poweroff_chance=0)
        desk = Desk("desk-1", "Test desk", "Test", collision_chance=0)
        other = Desk("desk-2", "Other desk", "Test", collision_chance=0)
        manager.desks = {desk.desk_id: desk, other.desk_id: other}

        class Handler(SimpleRESTServer):
            API_KEYS = ["test-key"]

            def __init__(self, *args, **kwargs):
                super().__init__(manager, *args, **kwargs)

            def log_message(self, *args):
                pass

        with HTTPServer(("127.0.0.1", 0), Handler) as simulator:
            thread = threading.Thread(target=simulator.serve_forever, daemon=True)
            thread.start()
            try:
                readings, commands = Mock(), Mock()
                readings.save_desk.return_value = 7
                commands.desk_exists.return_value = True
                commands.save_command.return_value = 8
                workflow = DeskWorkflow(
                    f"http://127.0.0.1:{simulator.server_port}", "test-key",
                    readings=readings, commands=commands, connect=Mock(),
                )
                with patch.dict(os.environ, {"DATABASE_URL": ""}), patch.dict(
                    app.dependency_overrides, {get_movement_workflow: lambda: workflow},
                ), TestClient(app) as client:
                    response = client.post("/api/desks/desk-1/height", json={"target_position_mm": 1000})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["status"], "accepted")
                self.assertEqual(response.json()["command_id"], 8)
                commands.save_command.assert_called_once_with("desk-1", 1000, "accepted")
                readings.save_desk.assert_called_once()
                self.assertEqual(desk.get_target_position(), 1000)
                # Acceptance precedes movement; advance the real simulator one tick.
                self.assertEqual(desk.state["position_mm"], 680)
                desk.update()
                self.assertGreater(desk.state["position_mm"], 680)
                self.assertEqual(other.get_target_position(), 680)
            finally:
                simulator.shutdown()
                thread.join(timeout=5)
