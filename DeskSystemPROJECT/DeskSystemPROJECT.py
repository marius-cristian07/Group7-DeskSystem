# Entry point for terminal commands such as show, sync, and move.
# It makes package imports work when called as a script, then hands control to UI/cli.py.
# Use the repository's run.py instead when you want to start the development servers.


"""
Created by : Edris Fiazi
Created on : 21.10.2026
Purpose    : KAN-5 Retrieve and display current desk data from the WiFi2BLE simulator
"""

import sys
from pathlib import Path

# Keep the original script command working while the rest of the code uses
# package imports. This is the only entry point that needs to adjust the path.
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from DeskSystemPROJECT.UI.cli import main

if __name__ == "__main__":
    # Pass the CLI result back to the terminal: zero means success.
    sys.exit(main())
