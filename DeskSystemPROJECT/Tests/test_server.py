# Checks the routes and response format that React relies on.
# TestClient runs FastAPI in-process; simulator calls are mocked, so no servers are needed.

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from DeskSystemPROJECT.server import app
from DeskSystemPROJECT.Data.desk_api_client import DeskAPIError
from DeskSystemPROJECT.Tests.fixtures import sample_desk


class ServerTests(unittest.TestCase):
    def setUp(self):
        # Call FastAPI in-process; enterContext also closes the client after each test.
        self.client = self.enterContext(TestClient(app))
        self.enterContext(patch.dict("os.environ", {"DESK_API_KEY": "test-key"}))

    def test_health_returns_ok(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_list_and_detail_keep_the_frontend_contract(self):
        record = sample_desk()
        expected = {
            "desk_id": record["desk_id"], "name": "DESK 4486",
            "position_mm": 1320, "speed_mms": 0, "status": "Normal",
            "is_anti_collision": False, "last_errors": record["lastErrors"],
        }
        with patch("DeskSystemPROJECT.server.get_desk_ids", return_value=[record["desk_id"]]), \
             patch("DeskSystemPROJECT.server.get_desk", return_value=record):
            self.assertEqual(self.client.get("/api/desks").json(), [expected])
            self.assertEqual(self.client.get(f"/api/desks/{record['desk_id']}").json(), expected)

    def test_empty_list_is_successful(self):
        with patch("DeskSystemPROJECT.server.get_desk_ids", return_value=[]):
            response = self.client.get("/api/desks")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_missing_key_is_503(self):
        with patch.dict("os.environ", {"DESK_API_KEY": ""}):
            for route in ("/api/desks", "/api/desks/missing"):
                self.assertEqual(self.client.get(route).status_code, 503)

    def test_missing_single_desk_is_404(self):
        with patch("DeskSystemPROJECT.server.get_desk", side_effect=DeskAPIError("missing", 404)):
            response = self.client.get("/api/desks/missing")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Desk missing not found"})

    def test_failed_list_still_returns_502(self):
        # Preserve the current contract even if a desk goes offline mid-request.
        with patch("DeskSystemPROJECT.server.get_desk_ids", return_value=["missing"]), \
             patch("DeskSystemPROJECT.server.get_desk", side_effect=DeskAPIError("missing", 404)):
            response = self.client.get("/api/desks")
        self.assertEqual(response.status_code, 502)

    def test_simulator_connection_failure_is_502(self):
        with patch("DeskSystemPROJECT.server.get_desk_ids", side_effect=DeskAPIError("offline")):
            response = self.client.get("/api/desks")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json(), {"detail": "offline"})

    def test_frontend_origin_is_allowed(self):
        response = self.client.get("/api/health", headers={"Origin": "http://127.0.0.1:5173"})
        self.assertEqual(response.headers["access-control-allow-origin"], "http://127.0.0.1:5173")


if __name__ == "__main__":
    unittest.main()
