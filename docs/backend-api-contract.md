# Backend API Contract

Base URL: `http://localhost:8080`

## Health Check

`GET /api/health`

Returns HTTP `200` when the backend is available:

```json
{
  "status": "ok"
}
```

## List Desks

`GET /api/desks`

Returns an array of desk objects. This endpoint is part of the agreed contract
and may be implemented separately:

```json
[
  {
    "desk_id": "desk-1",
    "name": "Office Desk",
    "position_mm": 720,
    "speed_mms": 0,
    "status": "Normal",
    "is_anti_collision": false,
    "last_errors": []
  }
]
```

Each object has these fields:

| Field | Type |
| --- | --- |
| `desk_id` | string |
| `name` | string |
| `position_mm` | integer |
| `speed_mms` | integer |
| `status` | string |
| `is_anti_collision` | boolean |
| `last_errors` | array |

## Errors

Errors use a JSON object with a `detail` message. The HTTP status code indicates
the kind of error:

```json
{
  "detail": "A description of the error"
}
```

Common status codes are `400` (invalid request), `404` (resource not found),
and `500` (unexpected server error).