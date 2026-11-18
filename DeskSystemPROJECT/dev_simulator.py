# Small adapter used by run.py to launch the simulator submodule.
# It runs the simulator's own main.py with its imports available and translates
# Windows shutdown signals so the simulator can save its state before exiting.

"""Run the external simulator without changing its source files."""

from contextlib import chdir
import runpy
import shutil
import signal
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def main():
    # Windows sends Ctrl+Break to a child process group during launcher cleanup.
    # Turn it into Ctrl+C so the simulator gets to save its state before exiting.
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, signal.default_int_handler)

    # The launcher sets the working directory to the simulator checkout.
    simulator = Path.cwd() / "simulator"
    sys.path.insert(0, str(simulator))
    # Run the simulator as a script so its normal startup and cleanup still apply.
    entry = str(simulator / "main.py")
    if "--stable-simulator" in sys.argv:
        sys.argv.remove("--stable-simulator")
        sys.argv.extend(["--no-user-simulation", "--desk-collision-chance", "0",
                         "--desk-poweroff-chance", "0"])
        # The simulator loads settings from its state file ahead of CLI defaults.
        # A fresh working directory also isolates its automatic save on shutdown.
        with TemporaryDirectory(prefix="desk-demo-") as folder:
            session = Path(folder)
            (session / "data").mkdir()
            (session / "config").mkdir()
            shutil.copyfile(simulator.parent / "config/api_keys.json", session / "config/api_keys.json")
            with chdir(session):
                runpy.run_path(entry, run_name="__main__")
    else:
        runpy.run_path(entry, run_name="__main__")


if __name__ == "__main__":
    main()
