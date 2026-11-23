# S6 fault classification and movement results

`Domain/desk_faults.py` contains the shared rules used by individual movement,
group preflight, group dispatch and group monitoring.

## Current condition

A normal status with no active flags is healthy. Collision, position loss,
overload protection in either direction, or another fault status makes the desk
faulty. The prototype blocks new commands in both directions for every active
fault, even if a particular protection flag names only one direction.

A missing reading is unavailable. Empty, unknown, unavailable, offline and
unreachable statuses are uncertain. These conditions also block new commands,
without claiming that the desk is mechanically broken. An active fault flag is
still evidence of a fault even if the status is uncertain.

`lastErrors` is historical evidence and never decides the current condition.
Snapshots keep these entries with their original time and code. Repeated entries
can occur in multiple snapshots and must not be counted as new incidents merely
because another snapshot contains them. No new incident table is introduced.

## Movement results

Command `status` still means accepted, failed or unknown. Acceptance does not mean
that the desk reached its target. The individual response adds `movement_outcome`,
`fault_codes`, `last_position_mm`, `last_speed_mms` and `at_target`.

Both movement paths check faults before declaring `reached`. A reading at the
target with a collision has `at_target: true` and outcome `desk_error`. A clean
success requires no current fault, a normal status, position within 2 mm of the
accepted target and zero observed speed. Group monitoring uses its configured
tolerance, which defaults to 2 mm.

The individual endpoint takes one fresh reading after acceptance. It can report
`moving`, which is not a promise of eventual completion. Group operations continue
polling. If a fault appears, that desk gets `desk_error` with its observed position,
speed and fault codes. No resend, reverse or stop command is sent. A zero speed
reading describes that observation only and does not guarantee a later stop.

## Evidence and cleaning recovery

Blocked fault readings, individual follow up readings and every successful group
poll are saved using the existing reading repository. This retains current flags,
positions and historical error entries after restart, including entries from
intermediate polls. The history endpoint now returns all four stored fault flags.
Storage failures are reported separately and cannot be treated as saved evidence.

A group with any fault or uncertain result cannot complete successfully. Existing
cleaning recovery maps failed and partially failed movements to `needs_review`,
so it cannot automatically return desks after a faulty raise. Interrupted runs
also require review after restart.

Detailed group operation views still live in memory. This task does not add
persistent group operation results or a manager resolution endpoint. Saved desk
readings and cleaning run review status use the existing database tables.
