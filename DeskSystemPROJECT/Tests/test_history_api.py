
"""Unit tests for the desk history API."""

import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from DeskSystemPROJECT.Data.database import DatabaseError
from DeskSystemPROJECT.server import app


class HistoryAPITests(unittest.TestCase):

    def setUp(self):
        # Disable background database collection during tests.
        self.enterContext(
            patch.dict(os.environ, {"DATABASE_URL": ""})
        )

        self.client = self.enterContext(TestClient(app))
        self.desk_id = "test-desk"

        # Replace real database functions with mocks.
        self.desk_exists = self.enterContext(
            patch(
                "DeskSystemPROJECT.server.desk_exists",
                return_value=True,
            )
        )

        self.readings = self.enterContext(
            patch(
                "DeskSystemPROJECT.server.get_desk_readings",
                return_value=[],
            )
        )

        self.commands = self.enterContext(
            patch(
                "DeskSystemPROJECT.server.get_desk_commands",
                return_value=[],
            )
        )

    def test_history_returns_readings_with_errors(self):
        self.readings.return_value = [
            {
                "reading_id": 1,
                "desk_id": self.desk_id,
                "recorded_at": "2026-10-27T10:03:27+01:00",
                "position_mm": 1100,
                "speed_mms": 0,
                "status": "Normal",
                "errors": [
                    {
                        "error_index": 0,
                        "time_s": 2695,
                        "error_code": 93,
                    }
                ],
            }
        ]

        response = self.client.get(
            f"/api/desks/{self.desk_id}/history"
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["desk_id"], self.desk_id)
        self.assertEqual(data["readings"][0]["position_mm"], 1100)
        self.assertEqual(
            data["readings"][0]["errors"][0]["error_code"],
            93,
        )

    def test_commands_returns_saved_commands(self):
        self.commands.return_value = [
            {
                "command_id": 1,
                "desk_id": self.desk_id,
                "requested_at": "2026-10-27T10:07:36+01:00",
                "target_position_mm": 1200,
                "status": "pending",
            }
        ]

        response = self.client.get(
            f"/api/desks/{self.desk_id}/commands"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["commands"][0]["target_position_mm"],
            1200,
        )

    def test_empty_history_returns_200(self):
        for endpoint, field in (
            ("history", "readings"),
            ("commands", "commands"),
        ):
            with self.subTest(endpoint=endpoint):
                response = self.client.get(
                    f"/api/desks/{self.desk_id}/{endpoint}"
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()[field], [])

    def test_unknown_desk_returns_404(self):
        self.desk_exists.return_value = False

        for endpoint in ("history", "commands"):
            with self.subTest(endpoint=endpoint):
                response = self.client.get(
                    f"/api/desks/{self.desk_id}/{endpoint}"
                )

                self.assertEqual(response.status_code, 404)

        self.readings.assert_not_called()
        self.commands.assert_not_called()

    def test_invalid_parameters_return_422(self):
        invalid_parameters = [
            {"limit": 0},
            {"limit": 1001},
            {"start": "invalid-date"},
            {"start": "2026-10-27T10:00:00"},
            {
                "start": "2026-11-12T12:00:00Z",
                "end": "2026-11-11T12:00:00Z",
            },
        ]

        for endpoint in ("history", "commands"):
            for params in invalid_parameters:
                with self.subTest(
                    endpoint=endpoint,
                    params=params,
                ):
                    response = self.client.get(
                        f"/api/desks/{self.desk_id}/{endpoint}",
                        params=params,
                    )

                    self.assertEqual(response.status_code, 422)

    def test_date_filters_reach_repository(self):
        params = {
            "start": "2026-10-27T00:00:00Z",
            "end": "2026-10-28T00:00:00Z",
            "limit": 5,
        }

        for endpoint, repository in (
            ("history", self.readings),
            ("commands", self.commands),
        ):
            with self.subTest(endpoint=endpoint):
                repository.reset_mock()

                response = self.client.get(
                    f"/api/desks/{self.desk_id}/{endpoint}",
                    params=params,
                )

                self.assertEqual(response.status_code, 200)

                repository.assert_called_once_with(
                    self.desk_id,
                    start=datetime(
                        2026, 10, 27, tzinfo=timezone.utc
                    ),
                    end=datetime(
                        2026, 10, 28, tzinfo=timezone.utc
                    ),
                    limit=5,
                )

    def test_database_failure_returns_503(self):
        self.desk_exists.side_effect = DatabaseError(
            "Private database connection details"
        )

        # Suppress expected traceback logging.
        with patch("DeskSystemPROJECT.server.logger"):
            for endpoint in ("history", "commands"):
                with self.subTest(endpoint=endpoint):
                    response = self.client.get(
                        f"/api/desks/{self.desk_id}/{endpoint}"
                    )

                    self.assertEqual(response.status_code, 503)
                    self.assertNotIn(
                        "Private database connection details",
                        response.text,
                    )

    def test_history_works_without_simulator(self):
        with patch(
            "DeskSystemPROJECT.server.get_api_config",
            side_effect=AssertionError(
                "History must not contact simulator"
            ),
        ):
            for endpoint in ("history", "commands"):
                with self.subTest(endpoint=endpoint):
                    response = self.client.get(
                        f"/api/desks/{self.desk_id}/{endpoint}"
                    )

                    self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
