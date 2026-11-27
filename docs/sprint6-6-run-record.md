# Sprint 6-6 — Test run record

Run in the provided project workspace on 2026-11-27.

| Check | Result | Notes |
|---|---|---|
| Backend pytest suite | **101 passed, 5 skipped** | Non-database tests ran with temporary import stubs for unavailable `psycopg2` and `pyserial` packages. The stubs were outside the project and are not included in the repository. No PostgreSQL test was treated as passed. |
| PostgreSQL persistence | **Not verified** | Three persistence tests skipped because `TEST_DATABASE_URL` was not configured. Must run against a disposable database ending in `_test`. |
| Live launcher integration | **Not verified** | Opt-in test skipped; no live app was launched. |
| Simulator HTTP integration | **Not verified** | Opt-in test skipped; no simulator movement was performed. |
| Frontend Node tests | **18 passed** | `npm --prefix frontend test` completed successfully. |
| Frontend production build | **Not verified** | `npm --prefix frontend run build` could not start because `vite` was not installed in the extracted environment (`sh: vite: not found`). Install the frontend dependencies in the team's normal environment and rerun. |
| Pico physical verification | **Not verified** | Requires the actual board, wiring, and manual checklist in `sprint6-6-verification.md`. |

## Automated coverage added

`DeskSystemPROJECT/Tests/test_s6_6_acceptance.py` adds deterministic cross-component acceptance checks for:

- each reported desk fault flag;
- collision at the target height;
- unknown/unavailable readings blocking movement;
- review resolution recording evidence and notifying the group service without movement;
- acknowledgement remaining distinct from resolution.

Existing regression coverage is retained for collision-at-target in single/group movement, operation persistence/restart, interrupted operation recovery, cleaning scheduler states, and history access without the live simulator.

## Next required verification

Run the PostgreSQL, optional simulator, frontend build, and Pico checks in the team's configured development environment. Update the acceptance checklist with the actual test output and evidence. Do not mark the skipped or unavailable checks as passed.
