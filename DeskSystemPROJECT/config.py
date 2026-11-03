# Shared defaults for run.py, the HTTP server, and the command-line tool.
# get_simulator_config reads process environment variables; it does not load .env files.
# The launcher supplies the simulator address and key to the backend when starting it.

"""Shared local addresses and simulator configuration."""

import os

SIMULATOR_PORT = 8000
BACKEND_PORT = 8080
FRONTEND_PORT = 5173

# The numeric loopback address avoids the slow localhost fallback on Windows.
DEFAULT_BASE_URL = f"http://127.0.0.1:{SIMULATOR_PORT}"


def get_simulator_config(env=None):
    # Tests can supply settings directly; normal runs read the terminal environment.
    env = os.environ if env is None else env
    return env.get("DESK_API_BASE_URL", DEFAULT_BASE_URL), env.get("DESK_API_KEY")
