# Optional end-to-end check of the launcher, simulator, and HTTP backend.
# It starts real services using temporary simulator data and checks that a height change
# reaches the backend. It does not test browser rendering or PostgreSQL writes.

"""Optional launcher smoke test using a temporary copy of the simulator."""

import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import URLError
from urllib.request import urlopen

from DeskSystemPROJECT.Data.desk_api_client import set_desk_height

ROOT = Path(__file__).resolve().parents[2]


# This test starts real services, so it only runs when explicitly enabled.
@unittest.skipUnless(os.environ.get("DESK_RUN_LIVE_TESTS") == "1", "Set DESK_RUN_LIVE_TESTS=1 to start the local services")
class LauncherIntegrationTests(unittest.TestCase):
    def test_start_read_move_and_stop(self):
        for port in (8000, 8080, 5173):
            with socket.socket() as listener:
                try:
                    listener.bind(("127.0.0.1", port))
                except OSError:
                    self.skipTest(f"Port {port} is already in use")

        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            simulator = temporary / "simulator-copy"
            shutil.copytree(ROOT / "wifi2ble-box-simulator/simulator", simulator / "simulator",
                            ignore=shutil.ignore_patterns("__pycache__"))
            (simulator / "config").mkdir()
            (simulator / "data").mkdir()
            key = "launcher-integration-test-key"
            (simulator / "config/api_keys.json").write_text(json.dumps([key]), encoding="utf-8")
            # Fresh, stable desks let this test move one without changing real data.
            state = {"current_time_s": 0, "simulation_speed": 60, "collision_chance": 0, "poweroff_chance": 0}
            (simulator / "data/desks_state.json").write_text(json.dumps(state), encoding="utf-8")
            env = os.environ.copy()
            env.pop("DESK_API_KEY", None)
            options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
            command = [sys.executable, "-c",
                       "import run, sys; from pathlib import Path; run.SIMULATOR = Path(sys.argv[1]); raise SystemExit(run.main())",
                       str(simulator)]
            log_path = temporary / "launcher.log"
            # Write logs to a file so unread pipe output cannot stall a child process.
            with log_path.open("w", encoding="utf-8") as log:
                process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, **options)
                try:
                    deadline = time.monotonic() + 30
                    while True:
                        self.assertIsNone(process.poll(), "Launcher exited before the frontend was ready")
                        try:
                            with urlopen("http://127.0.0.1:5173", timeout=1) as response:
                                self.assertIn('id="root"', response.read().decode())
                            break
                        except (OSError, URLError):
                            if time.monotonic() >= deadline:
                                self.fail("Frontend did not become ready")
                            time.sleep(0.2)

                    with urlopen("http://127.0.0.1:8080/api/desks", timeout=5) as response:
                        desks = json.load(response)
                    self.assertEqual(len(desks), 2)
                    desk = desks[0]
                    set_desk_height("http://127.0.0.1:8000", key, desk["desk_id"], 800)
                    deadline = time.monotonic() + 5
                    while True:
                        with urlopen(f"http://127.0.0.1:8080/api/desks/{desk['desk_id']}", timeout=5) as response:
                            updated = json.load(response)
                        if updated["position_mm"] != desk["position_mm"]:
                            break
                        if time.monotonic() >= deadline:
                            self.fail("The changed simulator height did not reach the backend")
                        time.sleep(0.2)
                # Stop the launcher and its children even when an assertion fails.
                finally:
                    if process.poll() is None:
                        if os.name == "nt":
                            process.send_signal(signal.CTRL_BREAK_EVENT)
                        else:
                            os.killpg(process.pid, signal.SIGINT)
                        try:
                            process.wait(timeout=15)
                        except subprocess.TimeoutExpired:
                            if os.name == "nt":
                                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
                            else:
                                process.kill()
                            process.wait()

            output = log_path.read_text(encoding="utf-8")
            self.assertEqual(process.returncode, 0, output)
            self.assertNotIn(key, output)
            self.assertIn("[redacted]", output)
            self.assertIn("state saved", output)
            self.assertNotIn("Traceback", output)
            for port in (8000, 8080, 5173):
                with socket.socket() as connection:
                    connection.settimeout(0.2)
                    self.assertNotEqual(connection.connect_ex(("127.0.0.1", port)), 0, f"Port {port} was left open")
