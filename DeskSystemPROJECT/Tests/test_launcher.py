# Checks startup order, shutdown, and which child receives the simulator key.
# Process creation is mocked; these tests inspect launcher behavior without starting services.

import contextlib
import io
import os
import unittest
from unittest.mock import Mock, patch

import run


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.enterContext(contextlib.redirect_stderr(io.StringIO()))
        self.enterContext(patch.object(run, "check_setup", return_value=("python", "node")))
        self.enterContext(patch.object(run, "read_api_key", return_value="private-key"))
        self.started = []

        # Record startup arguments without creating real server processes.
        def start(*args):
            process = Mock()
            process.poll.return_value = None
            self.started.append(args)
            return process, Mock()

        self.enterContext(patch.object(run, "start_process", side_effect=start))
        self.ready = self.enterContext(patch.object(run, "wait_until_ready"))
        self.stop = self.enterContext(patch.object(run, "stop_processes"))

    def test_ctrl_c_stops_all_services_and_only_backend_gets_key(self):
        # Interrupt the monitoring loop as if Ctrl+C had been pressed.
        with patch.dict(os.environ, {"DESK_API_KEY": "private-key", "DATABASE_URL": "private-db"}), \
             patch.object(run.time, "sleep", side_effect=KeyboardInterrupt):
            self.assertEqual(run.main(), 0)
        self.assertEqual([args[0] for args in self.started], ["simulator", "backend", "frontend"])
        self.assertEqual(len(self.stop.call_args.args[0]), 3)
        for name, _, _, env, _ in self.started:
            self.assertNotIn("DATABASE_URL", env)
            self.assertEqual(env.get("DESK_API_KEY"), "private-key" if name == "backend" else None)
        self.assertEqual(self.started[1][3]["DESK_API_BASE_URL"], "http://127.0.0.1:8000")
        self.assertEqual(self.started[2][3]["VITE_API_BASE_URL"], "http://127.0.0.1:8080")
        self.assertIn("--strictPort", self.started[2][1])

    def test_startup_failure_cleans_up_started_services(self):
        self.ready.side_effect = [None, RuntimeError("backend failed")]
        self.assertEqual(run.main(), 1)
        self.assertEqual([args[0] for args in self.started], ["simulator", "backend"])
        self.assertEqual(len(self.stop.call_args.args[0]), 2)

    def test_missing_dependencies_start_nothing(self):
        with patch.object(run, "check_setup", side_effect=RuntimeError("install first")):
            self.assertEqual(run.main(), 1)
        self.assertEqual(self.started, [])

    def test_log_redacts_simulator_key(self):
        output = io.StringIO()
        process = Mock(stdout=io.StringIO("GET /api/v2/private-key/desks\n"))
        with contextlib.redirect_stdout(output):
            run.print_output(process, "simulator", "private-key")
        self.assertNotIn("private-key", output.getvalue())
        self.assertIn("[simulator] GET /api/v2/[redacted]/desks", output.getvalue())
