# Simulator + PostgreSQL demo runbook

This demonstrates the existing CLI persistence and movement workflows alongside the web app.

## Prepare once

1. Complete [project setup](../SETUP.md), including the Python virtual environment and frontend dependencies.
2. Create `group7_desksystem` and apply `database/001_initial_schema.sql` using [the database guide](../database/SETUP.md). The tables are `desk`, `desk_readings`, `desk_errors`, and `desk_commands`.
3. Keep PostgreSQL running as your local service. Use your own credentials in `DATABASE_URL`.
4. Choose the machine for the demo and rehearse the commands below. Keep credentials out of screen sharing. The launcher redacts the simulator key in its combined log; the simulator's own manual log contains authenticated URLs.

## Start the app

From the repository root:

```powershell
python run.py
```

Open **http://127.0.0.1:5173** to show available desks. You can also show `http://127.0.0.1:8080/api/desks` for the backend JSON response; this address contains no simulator key.

The simulator may move desks and power them off during normal operation. For a more predictable exercise, use the manual simulator commands in [SETUP.md](../SETUP.md) with `--no-user-simulation --desk-poweroff-chance 0 --desk-collision-chance 0` instead of running the launcher. Saved collision and power-off settings in `wifi2ble-box-simulator/data/desks_state.json` override those flags; check them with the simulator stopped.

## Save a reading and request a height

In another PowerShell terminal at the repository root:

```powershell
$env:DESK_API_KEY = (Get-Content wifi2ble-box-simulator/config/api_keys.json -Raw | ConvertFrom-Json)[0]
$env:DATABASE_URL = 'postgresql://USERNAME:PASSWORD@127.0.0.1:5432/group7_desksystem'
.\.venv\Scripts\python.exe DeskSystemPROJECT/DeskSystemPROJECT.py show
.\.venv\Scripts\python.exe DeskSystemPROJECT/DeskSystemPROJECT.py sync
.\.venv\Scripts\python.exe DeskSystemPROJECT/DeskSystemPROJECT.py move DESK_ID 1000
```

Replace the database placeholders with your credentials and `DESK_ID` with an available ID printed by `show`. On macOS/Linux, use `.venv/bin/python`.

`show` is read-only. `sync` stores a new snapshot for each available desk. `move` records the requested height and its accepted/failed result; an accepted request also triggers a follow-up reading. Movement is gradual, so that reading may show a height between the starting point and the target.

## Verify PostgreSQL

In pgAdmin's Query Tool, confirm the selected database:

```sql
SELECT current_database(), current_user;
```

Then inspect the rows for the desk used in the demo, replacing `REPLACE_WITH_DESK_ID`:

```sql
SELECT desk_id, name, manufacturer
FROM desk
WHERE desk_id = 'REPLACE_WITH_DESK_ID';

SELECT reading_id, desk_id, position_mm, speed_mms, status, recorded_at
FROM desk_readings
WHERE desk_id = 'REPLACE_WITH_DESK_ID'
ORDER BY reading_id DESC
LIMIT 5;

SELECT command_id, desk_id, target_position_mm, status, requested_at
FROM desk_commands
WHERE desk_id = 'REPLACE_WITH_DESK_ID'
ORDER BY command_id DESC
LIMIT 5;
```

Repeated syncs update the desk's identity row and append new readings. They do not overwrite earlier snapshots. The command row keeps the requested target even if the simulator adjusts it to its movement limits.

A successful web API response alone does not demonstrate persistence: the current HTTP routes do not write to PostgreSQL. The saved rows above verify the CLI's database work.

Stop the services with Ctrl+C in the launcher terminal when finished. PostgreSQL stays running. For failure cases and exit codes, see [the workflow guide](sprint2-workflow.md).
