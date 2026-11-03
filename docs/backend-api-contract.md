# Backend API Contract

Base URL: `http://localhost:8080`

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
| `DESK_API_BASE_URL` | Simulator address, default: `http://localhost:8000` |
| `DESK_API_KEY` | API key required to access the simulator |

The simulator API key is only used by the Python backend and is not sent to the React frontend.

## Testing

The endpoints were manually tested using FastAPI Swagger UI at `http://localhost:8080/docs`.

Successful checks:

- `GET /api/health` returns HTTP `200`.
- `GET /api/desks` returns the current data of all 7 simulator desks.
- `GET /api/desks/{desk_id}` returns the requested desk.
- An unknown desk ID returns HTTP `404`.
- Stopping the simulator causes `GET /api/desks` to return HTTP `502`.

The endpoints return live simulator data. They do not read desk history from PostgreSQL.