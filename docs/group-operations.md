# Group operations (S5-1)

A group operation moves several desks to one height through one process that warns
first, can be cancelled, then sends the commands and reports what each desk really did.
The rules live in `DeskSystemPROJECT/Domain/group_operations.py`. The routes in
`group_operations_api.py` only translate HTTP. Each command is sent with the same
`DeskWorkflow.request_height` as the CLI and `POST /api/desks/{id}/height`, so it is
validated, sent and recorded in `desk_commands` in exactly the same way. There is no
second copy of the movement logic.

## Life of an operation

```
pending_warning -> countdown -> dispatching -> monitoring -> completed
                                                          -> partial_failure
                                                          -> failed
pending_warning / countdown -> cancelled   (cancelled by a person; nothing sent)
pending_warning / countdown -> blocked     (warning not confirmed or stale; nothing sent)
dispatching -> blocked                     (no desk passed the final check; nothing sent)
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
| `blocked` | Stopped before any command: the warning was not acknowledged in time, was stale at the end of the countdown, or no desk passed the final check. |

`failed` is an addition to the suggested list: it separates "commands were sent but nothing
arrived" from `blocked`, where nothing was sent.

## Result of each desk

| `result` | Meaning |
|---|---|
| `pending` | Not sent yet. |
| `moving` | The simulator accepted the command. This is **not** success. |
| `reached` | A fresh reading shows the desk at the accepted target with speed 0. |
| `not_reached` | Accepted, but the desk was not at the target when monitoring stopped. It may still be moving. |
| `unverified` | Accepted, but no fresh reading could be taken at the end. The position is unknown. |
| `desk_error` | The desk reported an error (status other than Normal, or anti-collision) while moving. |
| `rejected` | The simulator explicitly rejected the command. |
| `unknown` | The outcome of the command is uncertain. The desk may have moved. **It is never retried and never reported as success.** |
| `not_sent` | Nothing was sent to this desk (for example it failed the final availability or error check). |
| `cancelled` | The operation was cancelled before dispatch. |

Each desk also reports the workflow's `command_status` (`accepted`, `failed`, `unknown`),
`command_id` (the `desk_commands` row), `accepted_position_mm`, and its last fresh reading.

## Warning process

1. `POST /api/group-operations` checks the input, the configuration, the database and every desk
   (available, no current error) and **only then** publishes the warning. A bad request creates
   nothing and sends nothing.
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

The dashboard acknowledges as `dashboard`. Only the USB board can acknowledge as `pico`.
Scheduled raises and returns always require the physical channel, including in dashboard demo mode.
The channel names are free-form (lowercase letters, digits, `-` and `_`); the required ones are
set with `GROUP_WARNING_REQUIRED_CHANNELS`.

## Dashboard operation list

The group dashboard polls `GET /api/group-operations` for all active operations
and the five latest finished results. This also recovers dispatch and monitoring
after a page reload. Each operation includes a `reason` for a manager request,
a scheduled cleaning raise or a scheduled return. The dashboard sends its
`dashboard` acknowledgement while a warning's cancel control is visible in the
foreground tab. The Pico uses its own channel.

## Cancelling

`POST /api/group-operations/{id}/cancel` works during `pending_warning` and `countdown` and
guarantees that no command is sent.

Cancelling and the countdown ending are both state changes made under one lock, so exactly one
of them takes effect. Once dispatch has started, cancelling returns HTTP 409
(`Movement commands have already been sent...`). **Cancelling is not an emergency stop** and
does not stop desks that are already moving. Cancelling twice is harmless.

## Conflicts

A desk can be part of only one active movement. From creation until the operation ends
(cancelled, blocked or finished), its desks are reserved. A second group operation that shares a
desk, and `POST /api/desks/{id}/height` for a reserved desk, return **HTTP 409** and send nothing.
The individual endpoint reserves its desk while it runs, so a group created at the same moment
is refused too.

Reservations only cover requests that pass through this backend. The CLI and the simulator's own
simulated users can still move a desk at any time. If that happens during monitoring, the desk is
reported as `not_reached` or `unverified` with its last reading rather than as a success.

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

- Operations are kept in memory (the 100 newest finished ones). Restarting the backend forgets
  them, and a warning that was running is not resumed. Every command is still in `desk_commands`.
  Run the backend as a single process.
- The endpoints have no authentication, like the other endpoints.
- At most 50 desks per operation, 8 commands sent in parallel.
- Nothing is retried. An uncertain command stays `unknown` until a person checks the desk.

## Try it

With the app running (`python run.py`), and `GROUP_WARNING_REQUIRED_CHANNELS=dashboard` if there is no Pico:

```powershell
$b = 'http://127.0.0.1:8080/api/group-operations'
$op = Invoke-RestMethod -Method Post -Uri $b -ContentType 'application/json' `
  -Body '{"desk_ids":["DESK_ID_1","DESK_ID_2"],"target_position_mm":1000}'
Invoke-RestMethod -Method Post -Uri "$b/$($op.operation_id)/acknowledge" -ContentType 'application/json' -Body '{"channel":"dashboard"}'
Invoke-RestMethod -Uri "$b/$($op.operation_id)"                       # poll this
Invoke-RestMethod -Method Post -Uri "$b/$($op.operation_id)/cancel"   # only before dispatch
```
