# Small adapter used by run.py to launch the simulator submodule.
# It runs the simulator's own main.py with its imports available and translates
# Windows shutdown signals so the simulator can save its state before exiting.

"""Run the external simulator without changing its source files."""

import runpy
import signal
import sys
from pathlib import Path


def main():
    # Windows sends Ctrl+Break to a child process group during launcher cleanup.
    # Turn it into Ctrl+C so the simulator gets to save its state before exiting.
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, signal.default_int_handler)

    # The launcher sets the working directory to the simulator checkout.
    simulator = Path.cwd() / "simulator"
    sys.path.insert(0, str(simulator))
    # Run the simulator as a script so its normal startup and cleanup still apply.
    runpy.run_path(str(simulator / "main.py"), run_name="__main__")


if __name__ == "__main__":
    main()
