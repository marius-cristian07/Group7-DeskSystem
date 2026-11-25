# S6-2 — Persistent Operations, Results and Incidents

## Purpose

Group operation results and desk incidents are stored in PostgreSQL so that detailed movement results remain available after a backend restart or in-memory pruning.

## Database migration

Apply `database/004_group_operation_persistence.sql` after migrations 001–003.

| Table | Purpose |
|---|---|
| `group_operations` | Operation ID, reason, target height, state, timestamps, failure details and review state. |
| `group_operation_desks` | Individual desk results, dispatch intent, command references, observed positions and fault codes. |
| `desk_incidents` | Fault categories, first and last observations, recovery information and review state. |

The existing command, reading, error and cleaning history tables are reused.

## Operation persistence

The group operation service saves:

- Operation creation and state transitions.
- Cancellation and blocking reasons.
- Dispatch intent before sending each movement command.
- Individual command outcomes and monitoring results.
- Final operation and desk results.

If operation creation or the transition to dispatching cannot be saved, movement is not started.

If dispatch intent cannot be saved, the corresponding movement command is not sent.

If the final result cannot be saved, the operation is reported as interrupted and requires review. New group operations are disabled until the backend restarts and storage recovery succeeds.

## Startup recovery

Unfinished operations are marked as `interrupted` with `review_state = needs_review`.

Desk results are recovered according to their last saved state:

| Previous result | Recovered result |
|---|---|
| `moving` | `unverified` |
| `pending` with dispatch intent | `unknown` |
| `pending` without dispatch intent | `not_sent` |
| Other results | Preserved |

Movement commands are never automatically resumed or retried.

If startup recovery fails, group movements and the automatic cleaning scheduler remain disabled.

## Desk incidents

Incidents are recorded in the same database transaction as desk readings.

Repeated observations of the same active fault update the existing incident instead of creating duplicates.

A confirmed recovery clears the active incident. A later occurrence creates a new incident. Uncertain readings do not establish recovery.

Historical `lastErrors` entries are not treated as new active faults.

## API

| Endpoint | Description |
|---|---|
| `GET /api/group-operations/{operation_id}` | Retrieve a live or saved operation. |
| `GET /api/group-operations/history` | Retrieve paginated operation history. |
| `GET /api/desk-incidents` | Retrieve paginated and filtered desk incidents. |

Operation responses include `review_state`. Desk results include `dispatch_intent_at`.

Historical operations cannot be cancelled or resumed. Warning timing values that were not persisted are returned as null.

## Testing

The implementation was tested using mocked workflows and an isolated PostgreSQL database named `s62_integration_test`.

Results:

- 17 existing regression tests passed.
- 7 new persistence tests using an in-memory store passed.
- 3 PostgreSQL integration tests passed.

No physical desk movement was required for these tests.

## Scope

Manager resolution workflows and dashboard integration are handled separately in S6-3 and S6-4.