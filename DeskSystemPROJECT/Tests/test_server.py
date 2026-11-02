import sys
from pathlib import Path
import unittest

from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parent.parent))

from server import app


class ServerTests(unittest.TestCase):
    def test_health_returns_ok(self):
        # TestClient sends a request directly to the app without starting a server.
        with TestClient(app) as client:
            response = client.get("/api/health")

        # Check both the HTTP success code and the response data.
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})


if __name__ == "__main__":
    unittest.main()