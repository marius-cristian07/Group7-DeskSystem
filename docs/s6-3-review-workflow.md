# S6-3 Cleaning failure handling and controlled recovery

`needs_review` is now a workflow, not just a label. A failure stops future automatic starts on the
affected desks until a manager reviews it and records a decision. Resolving never moves a desk.

## What blocks an automatic start

Before a new cleaning occurrence is claimed, `claim_cleaning_start` checks every desk of that
schedule (any schedule, not only the one that failed) for:

| Blocker | Blocks while |
|---|---|
| Cleaning run | status is `needs_review`, `raising`, `cleaning` or `returning` (matched through the schedule's desks and the desks of its raise/return operations) |
| Group operation | `review_state = needs_review`, or the operation is still active |
| Desk incident | the fault is active, or it is unresolved and happened during a group operation |

A blocked occurrence is stored as a run with status `blocked` and a `blocked_reason` that names the
items. No desk is moved. Missed starts (`needs_review` rows created when the backend was down) block
until resolved too. After resolution only future occurrences run; missed cycles are never replayed.

Incidents: a fault that appeared and cleared by itself with no group operation involved stays listed
for review (`blocks_starts: false`) but does not stop cleaning. Otherwise a simulator that flaps
collision flags would block every schedule permanently. Set `CLEANING_BLOCK_ON_ALL_UNRESOLVED_INCIDENTS=1`
to make every unresolved incident block.

## Partial failures

* Raising fails or is uncertain: the run goes to `needs_review`; the return phase is not started.
* Returning fails: the results are kept and the run goes to `needs_review`.
* A movement is never retried because its response was lost; the outcome stays "unknown" until reviewed.
* A refused start is `blocked`; a refused return is `needs_review`.

## Resolving

`POST /api/cleaning-schedules/runs/{run_id}/resolve`
`POST /api/group-operations/{operation_id}/resolve`
`POST /api/desk-incidents/{incident_id}/resolve`

```json
{ "decision": "inspected_ok", "explanation": "Checked both desks by hand, heights are correct.", "resolved_by": "Mia" }
```

* `decision` is one of `inspected_ok`, `moved_manually`, `fault_repaired`, `nothing_to_review`.
* `explanation` is required (10-1000 characters). `resolved_by` is optional free text (there are no logins).
* The backend reads every involved desk fresh. Each must be reachable, healthy and not moving, otherwise
  the answer is 409 and nothing changes. The readings are saved as evidence in `review_records.desk_checks`.
* Resolving a run also resolves its linked operations and cleared incidents (one record each).
* An incident that is still active cannot be resolved. Resolving sends no movement command; any
  follow-up movement is a separate request to the normal movement endpoints.

## Acknowledging is not resolving

`POST /api/desk-incidents/{incident_id}/acknowledge` with an optional `note` and `acknowledged_by`
records "I have seen this". The incident stays unresolved and keeps blocking. It does not clear
hardware flags, delete history or bypass an unavailable desk.

## Reading

* `GET /api/reviews/unresolved?desk_id=` lists runs, operations, incidents (each with `blocks_starts`) and `blocking_desk_ids`.
* `GET /api/reviews/records?subject_type=&subject_id=&limit=` lists decisions and acknowledgements, newest first.

## Concurrency

Migration `005` adds the review tables. Starting a cleaning occurrence takes an exclusive advisory lock
`(52002, 2)`, then the schedule row; saving a group operation and resolving take the same lock
(`save_operation` shared, claim and resolve exclusive). Lock order is always review lock first,
so two schedules sharing a desk cannot both start, and a start cannot slip past a resolution check.

## Setup

Apply once: `psql "$DATABASE_URL" -f database/005_review_workflow.sql`
Tests: `python -m pytest DeskSystemPROJECT/Tests/test_s6_3_review.py DeskSystemPROJECT/Tests/test_s6_3_review_db.py`
(the DB file needs `TEST_DATABASE_URL` ending in `_test`).
