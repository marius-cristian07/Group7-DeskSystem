# Loads the documented example desk record for repository, workflow, and server tests.
# Each call reads a fresh dictionary so one test's edits cannot affect the next test.

import json
from pathlib import Path


def sample_desk():
    path = Path(__file__).resolve().parents[2] / "docs/examples/desk-internal-record.json"
    # utf-8-sig also accepts the byte-order mark some Windows editors add.
    return json.loads(path.read_text(encoding="utf-8-sig"))
