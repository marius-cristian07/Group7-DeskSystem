# Development launcher, run from the repository with: python run.py
# Checks the local setup, then starts simulator -> backend -> React in that order.
# Each service runs as a child process; its logs appear in this terminal.
# Ctrl+C or a service failure stops the children. PostgreSQL is started separately.

"""Start the local simulator, Python backend, and React in one terminal."""

import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import urlopen

from DeskSystemPROJECT.config import BACKEND_PORT, FRONTEND_PORT, SIMULATOR_PORT

ROOT = Path(__file__).resolve().parent
SIMULATOR = ROOT / "wifi2ble-box-simulator"
FRONTEND = ROOT / "frontend"


def check_setup():
    """Check prerequisites before starting any processes."""
    # Prefer this checkout's virtual environment, even if it is not activated.
    python = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    python = str(python) if python.is_file() else sys.executable
    if not (SIMULATOR / "simulator/main.py").is_file():
        raise RuntimeError("Simulator is missing. Run: git submodule update --init --recursive")
    node = shutil.which("node")
    if not node or not (FRONTEND / "node_modules/vite/bin/vite.js").is_file():
        raise RuntimeError("Install Node.js and run npm install in frontend/. See SETUP.md.")
    result = subprocess.run(
        [python, "-c", "import fastapi, uvicorn"], capture_output=True, text=True,
    )
    if result.returncode:
        raise RuntimeError("Install the Python packages from requirements.txt. See SETUP.md.")
    for port in (SIMULATOR_PORT, BACKEND_PORT, FRONTEND_PORT):
        with socket.socket() as listener:
            try:
                listener.bind(("127.0.0.1", port))
            except OSError:
                raise RuntimeError(f"Port {port} is busy. Stop the existing server and try again.") from None
    return python, node


def read_api_key():
    """Use an explicit key when set, otherwise use the local simulator's first key."""
    if os.environ.get("DESK_API_KEY"):
        return os.environ["DESK_API_KEY"]
    try:
        keys = json.loads((SIMULATOR / "config/api_keys.json").read_text(encoding="utf-8"))
        if isinstance(keys, list) and keys and isinstance(keys[0], str) and keys[0].strip():
            return keys[0]
    except (OSError, ValueError):
        pass
    raise RuntimeError("No simulator key found. Check wifi2ble-box-simulator/config/api_keys.json.")


def print_output(process, name, api_key):
    # The simulator logs authenticated URLs. Hide the key in the combined log.
    for line in process.stdout:
        line = line.rstrip().replace(quote(api_key, safe=""), "[redacted]")
        print(f"[{name}] {line.replace(api_key, '[redacted]')}", flush=True)


def start_process(name, command, cwd, env, api_key):
    # Each child has its own group, so cleanup only stops processes we started.
    if os.name == "nt":
        options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    else:
        options = {"start_new_session": True}
    process = subprocess.Popen(
        command, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", **options,
    )
    # Drain each service's output in the background so startup can keep going.
    reader = threading.Thread(target=print_output, args=(process, name, api_key), daemon=True)
    reader.start()
    return process, reader


def wait_until_ready(name, port, path, processes):
    """Wait for startup, but fail promptly if any child exits."""
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        for child_name, process, _ in processes:
            if process.poll() is not None:
                raise RuntimeError(f"{child_name} exited with code {process.returncode}. Check its log above.")
        try:
            # The simulator has no health route here, so check its listening port.
            if path is None:
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    return
            else:
                with urlopen(f"http://127.0.0.1:{port}{path}", timeout=1) as response:
                    if response.status == 200:
                        return
        except (OSError, URLError):
            pass
        time.sleep(0.1)
    raise RuntimeError(f"{name} did not become ready within 30 seconds.")


def stop_processes(processes):
    """Give services a chance to close normally before forcing a stuck one out."""
    for _, process, _ in reversed(processes):
        if process.poll() is None:
            try:
                if os.name == "nt":
                    process.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    os.killpg(process.pid, signal.SIGINT)
            except OSError:
                pass
    for _, process, reader in reversed(processes):
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        reader.join(timeout=1)
        process.stdout.close()


def main():
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, signal.default_int_handler)
    # Vite prints Unicode symbols that older Windows terminal encodings reject.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    processes = []
    try:
        python, node = check_setup()
        api_key = read_api_key()
        database_url = os.environ.get("DATABASE_URL")
        # Only the backend needs application credentials. Vite receives an address.
        common_env = os.environ.copy()
        for variable in ("DESK_API_KEY", "DESK_API_BASE_URL", "DATABASE_URL"):
            common_env.pop(variable, None)
        common_env["PYTHONUNBUFFERED"] = "1"
        common_env["PYTHONIOENCODING"] = "utf-8"
        backend_env = {**common_env, "DESK_API_KEY": api_key, "DESK_API_BASE_URL": f"http://127.0.0.1:{SIMULATOR_PORT}"}
        if database_url:
            backend_env["DATABASE_URL"] = database_url
        frontend_env = {**common_env, "VITE_API_BASE_URL": f"http://127.0.0.1:{BACKEND_PORT}"}
        services = [
            (
                "simulator",
                [python, str(ROOT / "DeskSystemPROJECT/dev_simulator.py"), "--port", str(SIMULATOR_PORT)],
                SIMULATOR, common_env, SIMULATOR_PORT, None,
            ),
            (
                "backend",
                [python, "-m", "uvicorn", "DeskSystemPROJECT.server:app", "--host", "127.0.0.1", "--port", str(BACKEND_PORT)],
                ROOT, backend_env, BACKEND_PORT, "/api/health",
            ),
            # Starting Vite through Node avoids an extra npm shell process to clean up.
            (
                "frontend",
                [node, str(FRONTEND / "node_modules/vite/bin/vite.js"), "--host", "127.0.0.1", "--port", str(FRONTEND_PORT), "--strictPort"],
                FRONTEND, frontend_env, FRONTEND_PORT, "/",
            ),
        ]
        # Wait for each dependency before starting the next service.
        for name, command, cwd, env, port, path in services:
            print(f"Starting {name}...", flush=True)
            process, reader = start_process(name, command, cwd, env, api_key)
            processes.append((name, process, reader))
            wait_until_ready(name, port, path, processes)
        print(f"\nOpen http://127.0.0.1:{FRONTEND_PORT} — press Ctrl+C to stop all three services.\n", flush=True)
        while True:
            for name, process, _ in processes:
                if process.poll() is not None:
                    raise RuntimeError(f"{name} stopped. Shutting down the other services.")
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\nStopping services...", flush=True)
        return 0
    except (RuntimeError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    finally:
        # Also clean up when startup fails after only some services have started.
        stop_processes(processes)


if __name__ == "__main__":
    raise SystemExit(main())
