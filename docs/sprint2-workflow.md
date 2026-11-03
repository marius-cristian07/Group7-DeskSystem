# Sprint 2 workflow: sync and move (S2-5)

The existing CLI commands provide live reads, persistence, and movement requests:

| Command | What it does | Moves a desk? |
|---|---|---|
| `sync` | Fetches every available desk and saves a new reading for each | No |
| `move DESK_ID HEIGHT_MM` | Requests a height for one desk, records the request, then reads the desk again | Yes |
| `show` | Prints current desk data, saves nothing | No |

Starting the application with no command only prints the help text. A desk moves only when `move` is given **both** a desk ID and a target height.

## Before you start

1. Complete [project setup](../SETUP.md), then run `python run.py` from the repository root. This starts the simulator, backend, and React in one terminal. The same guide has simulator-only startup instructions for CLI exercises.
2. Create the database and apply `database/001_initial_schema.sql` ([database/SETUP.md](../database/SETUP.md)).
3. Open a separate terminal at the repository root for the optional CLI commands. The application services continue running in the launcher terminal.
4. In that CLI terminal, set:

```powershell
$keys = Get-Content .\wifi2ble-box-simulator\config\api_keys.json | ConvertFrom-Json
$env:DESK_API_KEY = $keys[0]
$env:DATABASE_URL = 'postgresql://USERNAME:PASSWORD@127.0.0.1:5432/group7_desksystem'
```

`DESK_API_BASE_URL` is optional and defaults to `http://127.0.0.1:8000`. The application does not read `.env` files; set the variables in the terminal. To run the simulator, backend, and web app together, use `python run.py` from the repository root; see [SETUP.md](../SETUP.md).

## Commands

```powershell
.\.venv\Scripts\python.exe DeskSystemPROJECT/DeskSystemPROJECT.py show
.\.venv\Scripts\python.exe DeskSystemPROJECT/DeskSystemPROJECT.py sync
.\.venv\Scripts\python.exe DeskSystemPROJECT/DeskSystemPROJECT.py move cd:fb:1a:53:fb:e6 1000
```

These examples use the Windows virtual environment interpreter. On macOS/Linux, use `.venv/bin/python`.

For a stable demo with custom simulator flags, use manual simulator startup instead of the launcher: add `--no-user-simulation --desk-poweroff-chance 0 --desk-collision-chance 0`. Existing saved collision and power-off settings in `wifi2ble-box-simulator/data/desks_state.json` override those two flags; check those settings with the simulator stopped if desks still collide or disappear.

### sync

```
Synchronising desks from http://127.0.0.1:8000 ...
Found 7 available desk(s).
  [saved]  DESK 4486 | cd:fb:1a:53:fb:e6 | 872 mm | Normal | reading #1
  ...
Sync finished: 7 saved, 0 failed.
```

A desk that cannot be fetched or saved is reported as `[FAILED]` and the remaining desks are still synced.

### move

Accepted:

```
Requesting 900 mm for desk 91:17:a4:3b:f4:4d ...
Request ACCEPTED: desk 91:17:a4:3b:f4:4d was asked to move to 900 mm.
  Recorded in desk_commands as command #9 (accepted).
  New reading #20 saved: DESK 6782 | 1256 mm | speed -32 mm/s | Normal
  (The desk moves gradually, so the reading can still show it on its way.)
```

Failed (here: wrong API key):

```
Request FAILED for desk cd:fb:1a:53:fb:e6: HTTP 401: Authentication failed
  Recorded in desk_commands as command #10 (failed).
```

Order of events for `move`:

1. The input is checked (desk ID not empty, height a whole number above 0), the database is reachable, and the desk is stored in the `desk` table. If the desk was never synchronised, it is fetched and its `desk` row is created (no reading is saved).
2. The request is sent to the simulator.
3. The result is saved in `desk_commands` as `accepted` or `failed`.
4. If it was accepted, the application waits (default 2 seconds, change with `--wait SECONDS`, `0` reads straight away), fetches the desk again and saves a new reading. The wait is there because the simulator moves desks once per second; a reading taken at the same instant would still show the desk standing still.

If any check in step 1 fails, the error ends with "Nothing was sent." and no desk moves. So a request is only sent when the database is reachable and the desk can be referenced by the `desk_commands` row.

## Things to know

- **Table name:** the schema calls the table `desk_commands` (plural). The story text says `desk_command`.
- **Status values:** `accepted` and `failed` (see [database-schema.md](database-schema.md)). The table has no column for the error text, so the reason is only printed.
- **Accepted can mean adjusted:** the simulator limits targets to the desk's range (680-1320 mm in the simulator). A request for 2000 mm is accepted, the application prints `The desk adjusted the target to 1320 mm`, and `desk_commands.target_position_mm` keeps the requested 2000.
- **Exit codes:** `0` everything worked, `1` something failed (also a rejected request), `2` wrong command-line arguments.
- **Failed with the simulator stopped:** for a desk already in the database, a request while the simulator is down is recorded as `failed` ("Connection failed or request timed out"). For a desk the database has never seen, nothing is sent or recorded.

## Checking the result in the database

```sql
SELECT command_id, desk_id, target_position_mm, status, requested_at FROM desk_commands ORDER BY command_id;
SELECT reading_id, desk_id, position_mm, speed_mms, recorded_at FROM desk_readings ORDER BY reading_id DESC LIMIT 10;
```
