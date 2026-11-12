# Backend API Contract

Base URL: `http://127.0.0.1:8080`

Start the local simulator, backend, and React together with `python run.py` from the repository root. See [SETUP.md](../SETUP.md) for installation and manual startup options.

This document describes the HTTP endpoints provided by the Python backend.

The backend retrieves live desk data from the WiFi2BLE simulator. The React frontend communicates with the backend without accessing the simulator directly.

## Health Check

`GET /api/health`

Returns HTTP `200` when the backend is running.

```json
{
  "status": "ok"
}
```

## List Desks

`GET /api/desks`

Returns HTTP `200` with an array containing the current state of all available desks.

Example response:

```json
[
  {
    "desk_id": "cd:fb:1a:53:fb:e6",
    "name": "DESK 4486",
    "position_mm": 680,
    "speed_mms": 0,
    "status": "Normal",
    "is_anti_collision": false,
    "last_errors": []
  }
]
```

Each desk object contains the following fields:

| Field | Type | Description |
| --- | --- | --- |
| `desk_id` | string | Unique desk identifier |
| `name` | string | Desk name |
| `position_mm` | integer | Current height in millimeters |
| `speed_mms` | integer | Current movement speed in mm/s |
| `status` | string | Current desk status |
| `is_anti_collision` | boolean | Anti-collision flag |
| `last_errors` | array | Recent errors reported by the simulator |

The endpoint uses the existing `get_desk_ids()` and `get_desk()` functions from `desk_api_client.py`.

The returned data is converted to the agreed backend response format.

An empty list is returned if no desks are available.

## Get Desk by ID

`GET /api/desks/{desk_id}`

Returns HTTP `200` with the current state of one specific desk.

The `desk_id` is passed as a URL parameter.

Example request:

`GET /api/desks/cd:fb:1a:53:fb:e6`

Example response:

```json
{
  "desk_id": "cd:fb:1a:53:fb:e6",
  "name": "DESK 4486",
  "position_mm": 680,
  "speed_mms": 0,
  "status": "Normal",
  "is_anti_collision": false,
  "last_errors": []
}
```

The response uses the same format as the List Desks endpoint but returns a single object instead of an array.

If the requested desk does not exist, the backend returns HTTP `404`.

Example:

```json
{
  "detail": "Desk fake not found"
}
```

## Desk Errors

The `last_errors` field contains recent errors reported by the simulator.

Each error has the following structure:

```json
{
  "time_s": 2043,
  "errorCode": 93
}
```

- `time_s` - Internal simulator time in seconds, not a Unix timestamp.
- `errorCode` - Error code returned by the simulator.

The array may be empty if there are no reported errors.

## Error Responses

Errors are returned as JSON objects containing a `detail` message.

Example:

```json
{
  "detail": "A description of the error"
}
```

Possible HTTP status codes:

| Code | Description |
| --- | --- |
| `200` | Request successful |
| `404` | Requested desk was not found |
| `502` | Simulator connection failed or returned invalid data |
| `503` | Simulator API key is not configured |
| `500` | Unexpected backend error |

When the simulator is unavailable, the backend returns HTTP `502`:

```json
{
  "detail": "Connection failed or request timed out"
}
```

## Configuration

The backend uses the following environment variables:

| Variable | Description |
| --- | --- |
| `DESK_API_BASE_URL` | Simulator address, default: `http://127.0.0.1:8000` |
| `DESK_API_KEY` | API key required to access the simulator |

The simulator API key is only used by the Python backend and is not sent to the React frontend.

## Testing

The endpoints can be inspected using FastAPI Swagger UI at `http://127.0.0.1:8080/docs`.

Successful checks:

- `GET /api/health` returns HTTP `200`.
- `GET /api/desks` returns the current data of available simulator desks. The earlier manual check returned seven; the count varies when simulated desks power off.
- `GET /api/desks/{desk_id}` returns the requested desk.
- An unknown desk ID returns HTTP `404`.
- Stopping the simulator causes `GET /api/desks` to return HTTP `502`.

The endpoints return live simulator data. They do not read desk history from PostgreSQL.

Automated route checks run with the Python test suite documented in [README.md](../README.md#checks). The optional launcher integration check uses temporary simulator data and verifies a height change through the live backend.


## Desk History API (S4-2)

Historical data is read from PostgreSQL, not from the live simulator.
Both endpoints remain available when the simulator is offline,
provided the database is accessible.

### Get Desk Readings

GET /api/desks/{desk_id}/history

Optional query parameters:

| Parameter | Type | Description |
| --- | --- | --- |
| start | ISO 8601 datetime | Inclusive start, timezone required |
| end | ISO 8601 datetime | Inclusive end, timezone required |
| limit | integer | Default 50, minimum 1, maximum 1000 |

Readings are ordered newest first by recorded_at, then reading_id.

Example response:

```json
{
  "desk_id": "cd:fb:1a:53:fb:e6",
  "readings": [
    {
      "reading_id": 1,
      "desk_id": "cd:fb:1a:53:fb:e6",
      "recorded_at": "2026-10-27T10:03:27.833163+01:00",
      "position_mm": 1100,
      "speed_mms": 0,
      "status": "Normal",
      "errors": [
        {
          "error_index": 0,
          "time_s": 2695,
          "error_code": 93
        }
      ]
    }
  ]
}
```

Every reading contains an errors array, which can be empty.

The time_s value comes from the simulator and is not a
wall-clock timestamp. Use recorded_at for calendar time.

### Get Desk Commands

GET /api/desks/{desk_id}/commands

Supports the same start, end and limit parameters.

Commands are ordered newest first by requested_at,
then command_id.

Example response:

```json
{
  "desk_id": "cd:fb:1a:53:fb:e6",
  "commands": [
    {
      "command_id": 1,
      "desk_id": "cd:fb:1a:53:fb:e6",
      "requested_at": "2026-10-27T10:07:36.380487+01:00",
      "target_position_mm": 1200,
      "status": "pending"
    }
  ]
}
```

A command records the requested height and status.
It does not prove that the desk reached the requested height.

### HTTP Status Codes

| Code | Meaning |
| --- | --- |
| 200 | Request successful, including empty history |
| 404 | Desk does not exist in PostgreSQL |
| 422 | Invalid date, date range or limit |
| 503 | History database unavailable |

An existing desk without records in the selected period
returns HTTP 200 with an empty readings or commands array.

### Database Requirements

Set DATABASE_URL to connect the backend to PostgreSQL.

The history database uses:
- database/001_initial_schema.sql
- database/002_history_indexes.sql

Database credentials must not be committed to GitHub.

### Testing

Run the History API unit tests:

python -m unittest DeskSystemPROJECT.Tests.test_history_api -v

Run the full Python test suite:

python -m unittest discover -s DeskSystemPROJECT/Tests

## Individual Desk Control (S4-3)

`POST /api/desks/{desk_id}/height`

Requests one explicit movement through the same `DeskWorkflow.request_height`
used by the CLI. It performs no scheduling, group movement, or automatic retry.

Request body:

```json
{"target_position_mm": 1000}
```

The permitted range is **680–1320 mm inclusive**, matching the simulator's
current default travel limits. This policy is shared with the CLI in
`Domain/desk_workflow.py`. JSON booleans, strings, floats, null, missing values,
and unexpected fields are rejected. Identifiers contain 1–128 ASCII letters,
digits, colons, underscores or hyphens, starting with a letter or digit.
The workflow verifies configuration, database availability, and current desk
availability before sending the movement command. Missing desk identities are
saved before the command is sent.

Example response (HTTP 200):

```json
{
  "desk_id": "cd:fb:1a:53:fb:e6",
  "requested_position_mm": 1000,
  "accepted_position_mm": 1000,
  "command_id": 42,
  "status": "accepted",
  "error": null,
  "recording_error": null,
  "follow_up_error": null,
  "reading_id": 123
}
```

`accepted` means the simulator acknowledged a target; it does **not** mean the
desk reached it. The accepted target can differ from the requested height.
The follow-up snapshot is taken immediately and may still show the old height.
Read the live desk endpoint to observe subsequent movement.

Attempted commands return HTTP 200 with a structured outcome:

- `accepted`: a valid target acknowledgement was received.
- `failed`: an explicit rejection was received (HTTP 400, 401, 403, 404, 405 or 422).
- `unknown`: acceptance could not be established, for example after a timeout,
  server error, or malformed acknowledgement. The desk may have moved.

All three outcomes are recorded in `desk_commands` when storage succeeds.
`command_id` is null if recording fails; `recording_error` describes that
failure separately. An accepted command also attempts a follow-up reading;
`reading_id` is null and `follow_up_error` is populated if that step fails.
Acceptance remains `accepted` even if either storage step fails. HTTP errors
and result messages never include raw database errors or credentials.
The existing TEXT status column supports `unknown` without a schema migration.

Before a movement command is sent, validation errors return 422, an unavailable
or missing desk returns 404, a simulator verification failure returns 502,
and configuration/database failures return 503. These preflight failures send
no movement command. Once a command has been attempted, inspect the response
body rather than treating HTTP 200 as proof of acceptance or completed motion.

Do not automatically retry this POST after an uncertain result or a lost HTTP
response. It is not idempotent; check live state and request history first.
No movement retry is performed by the backend or simulator client.

Try it in Swagger UI at `http://127.0.0.1:8080/docs`, or in PowerShell:

```powershell
Invoke-RestMethod -Method Post `
  -Uri 'http://127.0.0.1:8080/api/desks/DESK_ID/height' `
  -ContentType 'application/json' `
  -Body '{"target_position_mm":1000}'
```

Start the backend with `DATABASE_URL`, the database schema, and simulator
configuration as described in `database/SETUP.md`. The launcher supplies the
simulator key. This sprint adds the backend contract; dashboard controls can
call it when implemented.

Validation:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s DeskSystemPROJECT/Tests
$env:DESK_RUN_MOVEMENT_TESTS = '1'
.\.venv\Scripts\python.exe -m unittest DeskSystemPROJECT.Tests.test_movement_integration -v
Remove-Item Env:DESK_RUN_MOVEMENT_TESTS
```

The isolated integration check runs the real simulator HTTP handler and desk
model on a temporary port with test storage. It verifies one desk moves and
the other remains unchanged; it does not verify a live PostgreSQL write.
