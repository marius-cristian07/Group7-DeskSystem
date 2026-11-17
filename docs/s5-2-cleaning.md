# S5-2 Cleaning schedules — handover and safe local demo

## Implemented
- Versioned migration `database/003_cleaning_schedules.sql` (already present in the student's working branch; do not re-run on an existing DB).
- `cleaning_schedules`, `cleaning_schedule_desks`, `cleaning_runs` using existing `desk` records.
- GET, POST, PUT, disable; POST `/api/cleaning-schedules/runs/{run_id}/cancel` for a single run.
- Validation: heights 680–1320 mm, desks must exist, non-empty name and desk list, unique IDs, whole-minute schedule times, fixed `Europe/Copenhagen`; no overlapping active schedules for shared desks.
- Atomic PostgreSQL advisory transaction lock for overlapping schedule writes, schedule row lock for edits/claims, unique `(schedule_id, occurrence_date)` for run starts, compare-and-set return claim.
- One daily window per schedule, overnight support, UTC-aware `TIMESTAMPTZ` movement request timestamps, DST non-existent times are skipped and later recorded for review (not executed).
- No retry of uncertain movement. Interrupted `raising`, `cleaning`, `returning` become `needs_review` when enabled backend starts.
- S5-1 `GroupOperationService` handles both raising and returning warnings, required acknowledgement channels, countdown, dispatch, desk monitoring and cancellation before dispatch.

## Safe setup
- Install Python packages with `./.venv/Scripts/python.exe -m pip install -r requirements.txt` in PowerShell (uses `tzdata` on Windows).
- Keep `CLEANING_SCHEDULER_ENABLED` **unset or 0** while testing; no background scheduled commands will be created.
- Keep existing session `DATABASE_URL` set; never paste credentials into chat or commit `.env`.
- Run one backend process with one worker: S5-1 state lives in memory and warnings are not shared across workers.
- `python run.py` starts simulator, backend, frontend; backend inherits the environment variable `CLEANING_SCHEDULER_ENABLED` from the parent process.
- Only after all integration tests with the simulator and warning channels: set `$env:CLEANING_SCHEDULER_ENABLED = '1'` before `python run.py`. Disable again with `Remove-Item Env:CLEANING_SCHEDULER_ENABLED -ErrorAction SilentlyContinue`.

## API JSON example
`POST /api/cleaning-schedules`:

```json
{
  "name": "Night cleaning",
  "cleaning_height_mm": 1200,
  "return_height_mm": 720,
  "start_time": "22:00",
  "end_time": "06:00",
  "timezone": "Europe/Copenhagen",
  "desk_ids": ["cd:fb:1a:53:fb:e6"]
}
```

Read via `GET /api/cleaning-schedules` or `GET /api/cleaning-schedules/{schedule_id}`; edit with full `PUT`, disable with `POST /api/cleaning-schedules/{schedule_id}/disable`.
Cancel an occurrence via `POST /api/cleaning-schedules/runs/{run_id}/cancel`. Cancel cannot stop commands already dispatched. A cancellation in `cleaning` or `returning` may leave desks elevated, requiring manual inspection and safe movement.

## State transitions
- `raising` (claimed) -> `cleaning` only if S5-1 raise state is `completed`.
- Raise `cancelled`/`blocked` -> matching run state. Failure or uncertain outcome -> `needs_review`.
- `cleaning` -> `returning` only at the exact scheduled end minute, once; return uses S5-1 warning again. `returning` -> `completed` only on success; otherwise `needs_review`.
- `CLEANING_SCHEDULER_ENABLED=1` startup marks unfinished operations `needs_review` and does **not** replay them.
- Missed starts for schedules that already existed are recorded as `needs_review`. Overdue return requests also become `needs_review`. No late commands are issued.
- Disabling future starts does not prevent the authorized current return. Editing is blocked while a run is `raising`, `cleaning`, `returning` or `needs_review`.

## Tests
1. Offline tests: `./.venv/Scripts/python.exe -m unittest discover -s tests -p test_s5_2.py -v`. These mock S5-1 and DB.
2. Review DB migration and run manual SQL checks on disposable schedule rows; check cleanup.
3. With simulator only (not physical desks) and active Pico/dashboard channels, run a short future schedule and watch two separate group-operation warnings and desk movement results.
4. Stop/restart backend during warning / during cleaning: check `cleaning_runs.status='needs_review'` and no replay.
5. Test simultaneous conflicting POST/PUT and a disabled schedule with an already running return.

## Known limitations / coordination
- The simple first version supports `Europe/Copenhagen` and one daily window only. Fall-back repeated clock time uses the first occurrence; the `(schedule_id, occurrence_date)` uniqueness prevents a second launch.
- S5-1 group operation state and per-desk terminal results are currently **in memory**. S5-2 stores operation IDs but cannot resurrect detailed outcomes after a restart. Coordinate persistent operation tables with the owner of S5-1 rather than adding a competing schema. The conservative response is `needs_review`.
- Review states require a person to inspect actual desk positions and decide the next safe action; this sprint does not implement a resume/retry endpoint.
- Only one backend scheduler instance is supported for local demonstration. Do not run multiple workers.
- No authentication exists for the existing project endpoints. Do not expose this backend on a public network.
