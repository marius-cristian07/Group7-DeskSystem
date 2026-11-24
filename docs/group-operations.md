
# Group operations (S5-1, S6-2)

A group operation moves several desks to one height through one process that warns
first, can be cancelled, then sends the commands and reports what each desk really did.
The rules live in `DeskSystemPROJECT/Domain/group_operations.py`. The routes in
`group_operations_api.py` only translate HTTP. Each command is sent with the same
`DeskWorkflow.request_height` as the CLI and `POST /api/desks/{id}/height`, so it is
validated, sent and recorded in `desk_commands` in exactly the same way. There is no
second copy of the movement logic.

Since S6-2, group operations, individual desk results and desk incidents are
persisted in PostgreSQL. Detailed results remain available after a backend restart.

## Life of an operation

```
pending_warning -> countdown -> dispatching -> monitoring -> completed
                                                          -> partial_failure
                                                          -> failed
pending_warning / countdown -> cancelled   (cancelled by a person; nothing sent)
pending_warning / countdown -> blocked     (warning not confirmed or stale; nothing sent)
dispatching -> blocked                     (no desk passed the final check; nothing sent)
unfinished operation -> interrupted        (recovered after backend restart)
final storage failure -> interrupted       (final result could not be saved)
```

| State | Meaning |
|---|---|
| `pending_warning` | The warning is published. Waiting for every required channel to acknowledge it. |
| `countdown` | Every required channel acknowledged. Dispatch waits for the deadline and, when required, the Pico's final button check. |
| `dispatching` | The countdown ended. **Cancelling is no longer possible.** Commands are being sent. |
| `monitoring` | Commands were sent. Fresh readings are polled until each desk is at its target or time runs out. |
| `completed` | Every desk was confirmed at its target by a fresh reading. |
| `partial_failure` | At least one desk was confirmed at the target and at least one was not. |
| `failed` | Commands were attempted, but no desk was confirmed at the target. |
| `cancelled` | Cancelled before dispatch. No command was sent. |
| `blocked` | Stopped before any command: the warning was not acknowledged in time, was stale at the end of the countdown, storage was unavailable, or no desk passed the final check. |
| `interrupted` | An unfinished operation was recovered after a backend restart, or its final result could not be saved. Requires review. Commands are never automatically retried. |

`failed` is an addition to the suggested list: it separates "commands were sent but nothing
arrived" from `blocked`, where nothing was sent.

## Result of each desk

| `result` | Meaning |
|---|---|
| `pending` | Not sent yet. |
| `moving` | The simulator accepted the command. This is **not** success. |
| `reached` | A fresh reading shows the desk at the accepted target with speed 0. |
| `not_reached` | Accepted, but the desk was not at the target when monitoring stopped. It may still be moving. |
| `unverified` | Accepted, but the final position or successful completion could not be verified. |
| `desk_error` | The desk reported a current fault while moving. |
| `rejected` | The simulator explicitly rejected the command. |
| `unknown` | The outcome of the command is uncertain. The desk may have moved. **It is never retried and never reported as success.** |
| `not_sent` | Nothing was sent to this desk (for example it failed the final availability or error check, or its dispatch intent could not be saved). |
| `cancelled` | The operation was cancelled before dispatch. |

Each desk also reports the workflow's `command_status` (`accepted`, `failed`, `unknown`),
`command_id` (the `desk_commands` row), `accepted_position_mm`, and its last fresh reading.

Since S6-2, each desk result also includes `dispatch_intent_at`, which records when
the intention to send its movement command was saved. A dispatch intent does not
prove that the command was actually sent or accepted.

## Warning process

1. `POST /api/group-operations` checks the input, the configuration, the database and every desk
   (available, no current error) and **only then** publishes the warning. A bad request creates
   nothing and sends nothing. The operation must be successfully saved before the warning
   is published.
2. The dashboard reads the warning from the group API. When `DESK_PICO_PORT` is set,
   the backend sends the operation ID to the physical board over USB.
3. The board confirms that its outputs are active over USB. The dashboard uses
   `POST /api/group-operations/{id}/acknowledge` with `{"channel": "dashboard"}`.
   The countdown starts only when **every required channel** has acknowledged.
4. A channel should repeat its acknowledgement while the warning is showing (for example
   every few seconds). A channel whose last acknowledgement is older than
   `GROUP_WARNING_STALE_SECONDS` when the countdown ends counts as **stale** and blocks dispatch.
5. If a required channel never acknowledges within `GROUP_WARNING_ACK_TIMEOUT_SECONDS`, the
   operation is `blocked` with `blocked_code: warning_not_acknowledged`.
6. When the countdown ends, a required Pico must return a final clear result for the same
   operation. A latched button press cancels it. Missing confirmation blocks dispatch.
   Every desk is then checked again (available, no current error). Desks that
   fail are `not_sent`, the rest are sent. If none pass, the operation is `blocked`
   (`no_desks_ready`).
7. The transition to `dispatching` must be saved before movement commands are sent.
   Each desk's dispatch intent is saved before its individual command is sent.
   If the dispatch intent cannot be saved, no command is sent to that desk.

The dashboard acknowledges as `dashboard`. Only the USB board can acknowledge as `pico`.
Scheduled raises and returns always require the physical channel, including in dashboard demo mode.
The channel names are free-form (lowercase letters, digits, `-` and `_`); the required ones are
set with `GROUP_WARNING_REQUIRED_CHANNELS`.

## Dashboard operation list

The group dashboard polls `GET /api/group-operations` for all active operations
and the five latest finished results available in memory. This also recovers
dispatch and monitoring after a page reload. Each operation includes a `reason`
for a manager request, a scheduled cleaning raise or a scheduled return.
The dashboard sends its `dashboard` acknowledgement while a warning's cancel
control is visible in the foreground tab. The Pico uses its own channel.

Saved historical operations can be retrieved through
`GET /api/group-operations/history` or
`GET /api/group-operations/{operation_id}` after a backend restart.

## Cancelling

`POST /api/group-operations/{id}/cancel` works during `pending_warning` and `countdown` and
guarantees that no command is sent when cancellation succeeds.

Cancelling and the countdown ending are both state changes made under one lock, so exactly one
of them takes effect. Once dispatch has started, cancelling returns HTTP 409
(`Movement commands have already been sent...`). **Cancelling is not an emergency stop** and
does not stop desks that are already moving. Cancelling twice is harmless for
a live operation that is already cancelled.

Cancellation results are persisted in PostgreSQL. Historical operations cannot
be cancelled or resumed.

## Conflicts

A desk can be part of only one active movement. From creation until the operation ends
(cancelled, blocked or finished), its desks are reserved. A second group operation that shares a
desk, and `POST /api/desks/{id}/height` for a reserved desk, return **HTTP 409** and send nothing.
The individual endpoint reserves its desk while it runs, so a group created at the same moment
is refused too.

Reservations only cover requests that pass through this backend. The CLI and the simulator's own
simulated users can still move a desk at any time. If that happens during monitoring, the desk may
be reported as `not_reached` or `unverified` with its last reading rather than as a success.

## Persistent storage (S6-2)

Group operations and individual desk results are stored in PostgreSQL using
the following tables:

| Table | Purpose |
|---|---|
| `group_operations` | Operation state, reason, target height, timestamps, blocking information and review state. |
| `group_operation_desks` | Individual desk results, dispatch intent, command references, last observed positions and fault codes. |
| `desk_incidents` | Current and historical fault occurrences, observation counts and review information. |

The existing `desk_commands`, `desk_readings` and `desk_errors` tables are reused.

The service persists operation creation, state transitions, cancellation,
dispatch intent, command outcomes, monitoring results and final results.

If the final operation result cannot be saved, the service reports the operation
as `interrupted` with `review_state: needs_review` in memory. New group operations
are disabled until the backend restarts and storage recovery succeeds.

This does not stop movement commands that have already been sent.

Apply `database/004_group_operation_persistence.sql` after migrations 001-003.

## Startup recovery

Before group movements are enabled, the backend checks PostgreSQL for unfinished
group operations.

Operations in `pending_warning`, `countdown`, `dispatching` or `monitoring`
are marked as `interrupted` and require review.

Individual desk results are recovered as follows:

| Last saved result | Recovered result |
|---|---|
| `moving` | `unverified` |
| `pending` with dispatch intent | `unknown` |
| `pending` without dispatch intent | `not_sent` |
| Other results | Preserved |

No unfinished operation is automatically resumed, and no movement command
is automatically retried.

If startup recovery fails, group movements and the automatic cleaning scheduler
remain disabled until the backend is restarted and recovery succeeds.

## Review state

Group operation responses include a `review_state` field.

| Value | Meaning |
|---|---|
| `not_required` | The operation does not require review under the S6-2 classification. |
| `needs_review` | The operation failed, partially failed or was interrupted. |
| `resolved` | Reserved for the manager resolution workflow in S6-3. |

The manager resolution workflow is outside the scope of S6-2.

## Desk incidents

Current desk faults are recorded as incidents in PostgreSQL.

Repeated observations of the same active fault update the existing incident
instead of creating duplicates. When a confirmed recovery is observed, the
active incident is cleared. A later occurrence creates a new incident.

Uncertain readings do not establish recovery. Historical `lastErrors` entries
are not treated as new active faults.

When an incident is first recorded during an active group operation involving
that desk, it is linked to the operation.

Clearing an active fault does not automatically resolve its review state.

## Historical API

| Endpoint | Description |
|---|---|
| `GET /api/group-operations` | Active operations and recent results available in memory. |
| `GET /api/group-operations/{operation_id}` | Retrieve a live or previously saved operation. |
| `GET /api/group-operations/history` | Retrieve paginated group operation history. |
| `GET /api/desk-incidents` | Retrieve paginated and filtered desk incidents. |

Group operation history supports:

- `limit`: 1-100, default 20.
- `offset`: 0-100000, default 0.

Desk incident history supports:

- `desk_id`: filter by desk.
- `operation_id`: filter by related group operation.
- `active`: filter by whether the fault is still active.
- `limit`: 1-200, default 50.
- `offset`: 0-100000, default 0.

Historical warning timing values that were not persisted are returned as
`null`. Historical acknowledgements are returned as an empty list.

For more information, see [S6-2 persistence](s6-2-persistence.md).

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `GROUP_WARNING_COUNTDOWN_SECONDS` | `10` | Countdown after the warning is acknowledged. 10 is a demo value, not a requirement. |
| `GROUP_WARNING_ACK_TIMEOUT_SECONDS` | `15` | How long to wait for the required channels to acknowledge. |
| `GROUP_WARNING_STALE_SECONDS` | `15` | Maximum age of a channel's last acknowledgement when the countdown ends. Keep it above the interval at which channels repeat. |
| `GROUP_WARNING_REQUIRED_CHANNELS` | `pico,dashboard` | Comma-separated channels that must acknowledge. Use `dashboard` alone to test without a Pico. |
| `GROUP_MONITOR_TIMEOUT_SECONDS` | `60` | Longest time to wait for fresh readings after dispatch. |
| `GROUP_MONITOR_POLL_SECONDS` | `1` | Delay between fresh readings. |

An invalid value stops the backend at startup with a message naming the variable.

## Limits

- Active operations and the 100 newest finished operations are kept in memory.
  Saved operation history is persisted in PostgreSQL and remains available after
  a backend restart or in-memory pruning.
- Run the backend as a single process.
- The endpoints have no authentication, like the other endpoints.
- At most 50 desks per operation, 8 commands sent in parallel.
- Nothing is automatically retried. An uncertain command stays `unknown` until
  a person checks the desk.
- Manager resolution workflows and dashboard integration for persistent incidents
  are handled separately in S6-3 and S6-4.

## Try it

With the app running (`python run.py`), and `GROUP_WARNING_REQUIRED_CHANNELS=dashboard`
if there is no Pico.

Only send movement commands in an authorised test environment with a simulator
and a dedicated test database.

```powershell
$b = 'http://127.0.0.1:8080/api/group-operations'

$desks = @(Invoke-RestMethod -Uri 'http://127.0.0.1:8080/api/desks')

if ($desks.Count -lt 2) {
    throw 'At least two simulator desks are required'
}

$body = @{
    desk_ids = @($desks[0].desk_id, $desks[1].desk_id)
    target_position_mm = 1000
} | ConvertTo-Json

$op = Invoke-RestMethod -Method Post -Uri $b `
    -ContentType 'application/json' -Body $body

Invoke-RestMethod -Method Post `
    -Uri "$b/$($op.operation_id)/acknowledge" `
    -ContentType 'application/json' `
    -Body '{"channel":"dashboard"}'

Invoke-RestMethod -Uri "$b/$($op.operation_id)"

# Only before dispatch
Invoke-RestMethod -Method Post -Uri "$b/$($op.operation_id)/cancel"
```

Retrieve saved operation history:

```powershell
Invoke-RestMethod -Uri "$b/history?limit=20&offset=0"
```

Retrieve active desk incidents:

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8080/api/desk-incidents?active=true&limit=50'
```
