# Sprint 6-6 — Integration, failure-scenario tests and acceptance evidence

## Purpose

Verify the complete fault/recovery workflow using repeatable tests. The automated tests use deterministic fakes and do not send movement commands to real desks. Database integration is run only against a disposable PostgreSQL database whose name ends in `_test`. Physical Pico checks are manual and must be recorded separately.

## Automated checks

Run from the repository root in the project virtual environment.

### 1. Frontend unit tests

```bash
npm --prefix frontend test
```

This runs the Node built-in test runner for API-client and desk-status tests. The current suite verifies fault status priority, anti-collision and overload flags, stale historical errors, and API error handling.

### 2. Backend unit and integration tests

```bash
python -m pytest DeskSystemPROJECT/Tests -v
```

The default suite uses mocks/fakes for simulator and database calls. PostgreSQL tests skip unless `TEST_DATABASE_URL` is configured.

### 3. PostgreSQL persistence tests

Create a separate local database, for example `group7_desksystem_test`, apply no production data to it, and set:

```bash
# Linux/macOS
export TEST_DATABASE_URL="postgresql://USER:PASSWORD@127.0.0.1:5432/group7_desksystem_test"

# Windows PowerShell
$env:TEST_DATABASE_URL = "postgresql://USER:PASSWORD@127.0.0.1:5432/group7_desksystem_test"
```

Then run:

```bash
python -m pytest DeskSystemPROJECT/Tests/test_s6_2_persistence.py -v
```

The test fixture refuses database names that do not end in `_test`. It drops/recreates project tables, so never point this variable at a development or production database.

### 4. Optional simulator HTTP integration

The simulator integration tests are opt-in. Start only with the isolated test simulator setup described in `README.md` and the simulator documentation:

```bash
# Set this only when the isolated simulator is ready
export DESK_RUN_MOVEMENT_TESTS=1
python -m pytest DeskSystemPROJECT/Tests/test_movement_integration.py -v
```

The tests create in-memory simulator desks and use a temporary HTTP server; they must not load or overwrite a user's simulator state. Unset the variable afterward.

## Sprint 6 acceptance scenarios

| Scenario | Automated evidence | Result |
|---|---|---|
| Collision at target height is not reported as clean success | `test_desk_workflow.py`, `test_group_operations.py`, `test_s6_6_acceptance.py` | Record test run |
| Unresolved/uncertain cleaning run blocks unsafe automatic follow-up | `test_s5_2.py` and scheduler/review tests | Record test run + DB integration |
| Operation results survive service restart | `test_s6_2_persistence.py` memory-store restart test; PostgreSQL persistence test | Record test run + DB integration |
| Resolution requires fresh healthy desk checks and does not issue movement | `test_s6_6_acceptance.py` and review API tests | Record test run |
| Historical desk history is available without live simulator | `test_history_api.py` | Record test run |
| Frontend displays fault states consistently | `frontend/src/utils/deskStatus.test.js` | Record `npm test` |
| Pico warning/cancel works on the actual board | Manual hardware checklist below | Must be verified physically |

## Physical Pico checklist (manual; do not mark passed from mocks)

- [ ] Board connected before warning: expected active/countdown response received.
- [ ] USB removed before warning: warning device shown unavailable; dispatch is blocked.
- [ ] USB removed during countdown: missing final confirmation blocks dispatch.
- [ ] Pico reset during countdown: operation remains cancelled/uncertain; no stale release after reconnect.
- [ ] Button short press cancels; held press behaviour is recorded.
- [ ] Button press at countdown boundary is tested repeatedly.
- [ ] LED, buzzer and button wiring matches firmware constants.
- [ ] Wi-Fi health check works at the configured host/port; warning transport remains USB.
- [ ] Demonstration confirms button cancellation is not represented as a physical emergency stop after dispatch.

For every item, record tester, date/time, expected result, observed result, and evidence (test output, screenshot, or short video). Never mark a physical test passed based only on a mocked serial response.

## Test evidence record

Copy this table into the sprint report and fill in the actual results after running the checks.

| Check | Status (Passed / Failed / Not verified) | Evidence / issue link | Tester + date |
|---|---|---|---|
| Frontend tests | Not verified | | |
| Backend default tests | Not verified | | |
| PostgreSQL persistence | Not verified | | |
| Simulator integration | Not verified | | |
| Pico physical checklist | Not verified | | |

A test suite passing does not prove that the real desk's collision protection or physical stopping behaviour has been verified. Report unrun database, simulator, or hardware checks as **Not verified**, not Passed.
