# Desk data contract — Sprint 1

Owner: Marius. Status: proposed v1, awaiting agreement with Daniil (API client) and Edris (backend).

This document defines the desk data passed from the API client to the backend. It covers desk identity, name, position, status, usage counters, and error history. The proposal preserves the simulator's JSON structure and adds `desk_id` at the top level. In Python, this can be an ordinary dictionary containing dictionaries and a list; a custom class is not required for Sprint 1.

## Getting the data

1. Start the simulator using [SETUP.md](../SETUP.md), if it is not already running.
2. Call `GET http://localhost:8000/api/v2/<api_key>/desks`. The result is a JSON array of desk ID strings.
3. For each ID, call `GET http://localhost:8000/api/v2/<api_key>/desks/<desk_id>`.
4. Keep the ID used in the request: the successful response body does **not** contain it.

Replace the placeholders, including their angle brackets. Keep the API key in configuration; do not put it in the internal desk record or example files.

## Fields and meaning

The fields below are required and non-null in the proposed internal contract. The simulator normally supplies all the API fields, but its OpenAPI schema does not formally mark them as required. These requirements are our proposed application rules.

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

Use the successful API response unchanged for `config`, `state`, `usage`, and `lastErrors`, and add `desk_id`. Retain the existing camelCase names so Sprint 1 needs no field renaming or unit conversion.

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

An error response is not a desk record. Do not create a fake desk with zero height or a fabricated status. Powered-off desks are omitted from the list endpoint, and a desk can become unavailable between listing and fetching. The backend should report that individual fetch failure without presenting it as fresh desk data.

## Examples and evidence

- [desk-api-response.json](examples/desk-api-response.json): the successful detail response captured from the running local simulator.
- [desk-internal-record.json](examples/desk-internal-record.json): the same captured data plus the requested `desk_id`.

The examples are one saved snapshot, so later requests can return different heights, counters, or errors. No API key is included.

Field names/types were checked against [OpenAPI](../wifi2ble-box-simulator/docs/openapi.json), behavior against [desk.py](../wifi2ble-box-simulator/simulator/desk.py), availability against [desk_manager.py](../wifi2ble-box-simulator/simulator/desk_manager.py), and response handling against [simple_rest_server.py](../wifi2ble-box-simulator/simulator/simple_rest_server.py). The persisted `data/desks_state.json` includes extra simulator bookkeeping and is not the HTTP response contract.

## Team handoff

Marius proposes this format and owns this document and its examples. Edris and Martin should confirm that the client will return the defined record and the backend will consume it. Until they confirm, this is a proposal rather than an agreed team contract.

Review together: the added `desk_id`, preservation of API field names and units, required/non-null fields, and how fetch/validation failures reach the backend. Record the agreement and any changes here. Ivan can use the examples and validation rules for valid-response and failure-case tests.
