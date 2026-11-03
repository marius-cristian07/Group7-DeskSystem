# Desk data contract — Sprint 1

Owner: Marius. This document describes the internal format currently implemented by the Python API client and persistence code, originally proposed in Sprint 1.

This document defines the desk data passed from the simulator API client to the Python workflows and persistence code. It covers desk identity, name, position, status, usage counters, and error history. The record preserves the simulator's JSON structure and adds `desk_id` at the top level. Python represents it as a dictionary containing dictionaries and a list.

React receives a separate, flattened response described in [the backend API contract](backend-api-contract.md). It calls the Python backend and does not call the simulator directly.

## Getting the data

1. Start the simulator using [SETUP.md](../SETUP.md), if it is not already running.
2. The Python client calls `GET http://127.0.0.1:8000/api/v2/<api_key>/desks`. The result is a JSON array of desk ID strings.
3. For each ID, it calls `GET http://127.0.0.1:8000/api/v2/<api_key>/desks/<desk_id>`.
4. Keep the ID used in the request: the successful response body does **not** contain it.

Replace the placeholders, including their angle brackets. Keep the API key in configuration; do not put it in the internal desk record or example files.

## Fields and meaning

The fields below are required and non-null in the implemented internal contract. The simulator normally supplies all the API fields, but its OpenAPI schema does not formally mark them as required. The Python client's `validate_desk()` enforces these application rules.

- `desk_id`: string. Comes from the list endpoint and the detail request URL. Treat it as an opaque identifier, for example `cd:fb:1a:53:fb:e6`. Do not identify desks by their display names.
- `config`: object containing:
  - `name`: string, the desk's display name.
  - `manufacturer`: string, the manufacturer label.
- `state`: object containing:
  - `position_mm`: integer, current desk height in millimetres. The simulator's default movement limits are 680–1320 mm. Keep the value in millimetres; these limits are simulator defaults, not a universal validation rule.
  - `speed_mms`: integer, signed speed in millimetres per second. Positive means moving up, negative means moving down, and zero means stationary. The current simulator uses 32, -32, and 0.
  - `status`: string. The current simulator sets `Normal` or `Collision`. Preserve other strings for compatibility. `Normal` does not mean stationary or that there is no error history.
  - `isPositionLost`: boolean, position-lost flag. Initialized to false; this simulator does not actively simulate changes to it.
  - `isOverloadProtectionUp`: boolean, upward overload-protection flag. Initialized to false; not actively simulated.
  - `isOverloadProtectionDown`: boolean, downward overload-protection flag. Initialized to false; not actively simulated.
  - `isAntiCollision`: boolean, anti-collision flag. Set when a simulated collision occurs and cleared on a later successful movement update.
- `usage`: object containing:
  - `activationsCounter`: non-negative integer. Incremented when a requested target differs from the current position. It is not a count of completed movements; repeated requests can increment it.
  - `sitStandCounter`: non-negative integer. Incremented when movement crosses the simulator's midpoint in either direction (1000 mm with the default limits). It does not directly measure time spent sitting or standing.
- `lastErrors`: array of objects, each containing:
  - `time_s`: non-negative integer, the desk's internal simulator clock in seconds when the error was recorded. It is not a Unix timestamp, wall-clock date, or elapsed time since the error. The current clock is not included in the detail response, so error age cannot be calculated from this response alone.
  - `errorCode`: non-negative integer. The simulator generates 93 for collisions. Preserve unfamiliar codes rather than rejecting them or guessing a description.

The simulator prepends newly generated errors and retains at most ten entries during normal operation. Preserve the supplied order. An empty `lastErrors` array is valid; a missing or null array is not equivalent to an empty one. Historical errors can coexist with `status: "Normal"` and `isAntiCollision: false`.

The simulator initializes counters to 25 and 1 and includes an initial error entry. It can also restore persisted values. Do not assume that these values start at zero or describe activity only since your application started.

## Internal format and conversion

Use the successful API response unchanged for `config`, `state`, `usage`, and `lastErrors`, and add `desk_id`. The internal record retains the simulator's camelCase names and units; the HTTP backend separately formats its response for React.

Conceptual Python conversion, after checking the HTTP response and validating its fields:

```python
desk_record = {
    "desk_id": requested_desk_id,
    "config": response_json["config"],
    "state": response_json["state"],
    "usage": response_json["usage"],
    "lastErrors": response_json["lastErrors"],
}
```

This snippet describes the mapping; it is not a complete API client or validator. Treat the record as a snapshot and avoid modifying its nested objects after passing it to another component.

JSON objects map to Python dictionaries, arrays to lists, strings to `str`, integers to `int`, and booleans to `bool`. When validating integer fields in Python, exclude booleans (`bool` is a subclass of `int`).

Do not replace missing fields with zero, false, or empty strings. Report a parsing/validation failure with the desk ID and field path so incomplete data cannot look like a healthy desk. Unknown additional API fields may be ignored; the defined fields must retain their types. Keep numeric fields as integers under this v1 contract; malformed or fractional values need an explicit validation failure, not silent rounding.

## Failed requests and unavailable desks

- HTTP 400: request path/version problem; report it as a request failure.
- HTTP 401: invalid API key; report an authentication failure.
- HTTP 404 with `{"error": "Desk not found"}`: the ID is unknown or the desk is currently powered off. The response does not distinguish these cases.
- Connection failure or timeout: report that data could not be retrieved.

An error response is not a desk record. Do not create a fake desk with zero height or a fabricated status. Powered-off desks are omitted from the list endpoint, and a desk can become unavailable between listing and fetching. The CLI `show` and `sync` commands report individual failures and continue with other desks. The HTTP list endpoint currently returns 502 if any desk fetch fails; React clears its current data and retries automatically.

## Examples and evidence

- [desk-api-response.json](examples/desk-api-response.json): the successful detail response captured from the running local simulator.
- [desk-internal-record.json](examples/desk-internal-record.json): the same captured data plus the requested `desk_id`.

The examples are one saved snapshot, so later requests can return different heights, counters, or errors. No API key is included.

Field names/types were checked against [OpenAPI](../wifi2ble-box-simulator/docs/openapi.json), behavior against [desk.py](../wifi2ble-box-simulator/simulator/desk.py), availability against [desk_manager.py](../wifi2ble-box-simulator/simulator/desk_manager.py), and response handling against [simple_rest_server.py](../wifi2ble-box-simulator/simulator/simple_rest_server.py). The persisted `data/desks_state.json` includes extra simulator bookkeeping and is not the HTTP response contract.

## Team handoff

The client, workflows, and repositories now use this format. If the team changes it, update the validator, examples, persistence mapping, and tests together. Keep the internal simulator record distinct from the public React API response.
