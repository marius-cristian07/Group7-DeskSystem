# Database Schema

## Overview

This document describes the PostgreSQL database schema for the Smart Office Desk Coordination System.

The database stores desk information, readings, errors, and movement commands.

SQL schema: `database/001_initial_schema.sql`

Database name: `group7_desksystem`

## Tables

### 1. desk

Stores basic information about each desk.

| Column | Type | Description |
|---|---|---|
| desk_id | TEXT | Primary Key, unique desk ID |
| name | TEXT | Desk name |
| manufacturer | TEXT | Desk manufacturer |

The `desk_id` comes from the simulator and must be used to identify desks, not the desk name.

### 2. desk_readings

Stores desk state and usage information. A new row can be created each time the desk data is fetched.

| Column | Type | Description |
|---|---|---|
| reading_id | BIGINT | Auto-generated Primary Key |
| desk_id | TEXT | Foreign Key to desk |
| recorded_at | TIMESTAMPTZ | Automatically generated timestamp |
| position_mm | INTEGER | Current desk height in mm |
| speed_mms | INTEGER | Desk movement speed in mm/s |
| status | TEXT | Current desk status |
| activations_counter | INTEGER | Number of activations |
| sit_stand_counter | INTEGER | Number of sit/stand transitions |
| is_position_lost | BOOLEAN | Position lost flag |
| is_overload_protection_up | BOOLEAN | Upward overload protection |
| is_overload_protection_down | BOOLEAN | Downward overload protection |
| is_anti_collision | BOOLEAN | Anti-collision flag |

Both counters must be non-negative.

### 3. desk_errors

Stores errors reported in the `lastErrors` array of a reading.

| Column | Type | Description |
|---|---|---|
| error_id | BIGINT | Auto-generated Primary Key |
| reading_id | BIGINT | Foreign Key to desk_readings |
| error_index | INTEGER | Position in the lastErrors array, starting at 0 |
| time_s | INTEGER | Simulator time in seconds |
| error_code | INTEGER | Simulator error code |

`reading_id` and `error_index` must be unique together.

`time_s` is the simulator's internal clock, not a Unix timestamp.

The same historical error can appear in multiple readings because the simulator returns a list of recent errors.

### 4. desk_commands

Stores requests to change a desk's height.

| Column | Type | Description |
|---|---|---|
| command_id | BIGINT | Auto-generated Primary Key |
| desk_id | TEXT | Foreign Key to desk |
| requested_at | TIMESTAMPTZ | Automatically generated timestamp |
| target_position_mm | INTEGER | Requested height in mm, must be positive |
| status | TEXT | Command status |

The application creates command records separately from the desk-reading API. Command status values should be agreed with the backend team before integration.

## Relationships

- One desk can have many readings.
- One reading can have many reported errors.
- One desk can have many movement commands.

Foreign Keys prevent readings and commands from referencing desks that do not exist, and errors from referencing readings that do not exist.

## API to Database Mapping

The mapping follows the Sprint 1 desk data contract.

| API / Internal Record Field | Database Column |
|---|---|
| `desk_id` | `desk.desk_id` |
| `config.name` | `desk.name` |
| `config.manufacturer` | `desk.manufacturer` |
| `desk_id` | `desk_readings.desk_id` |
| `state.position_mm` | `desk_readings.position_mm` |
| `state.speed_mms` | `desk_readings.speed_mms` |
| `state.status` | `desk_readings.status` |
| `usage.activationsCounter` | `desk_readings.activations_counter` |
| `usage.sitStandCounter` | `desk_readings.sit_stand_counter` |
| `state.isPositionLost` | `desk_readings.is_position_lost` |
| `state.isOverloadProtectionUp` | `desk_readings.is_overload_protection_up` |
| `state.isOverloadProtectionDown` | `desk_readings.is_overload_protection_down` |
| `state.isAntiCollision` | `desk_readings.is_anti_collision` |
| `lastErrors[].time_s` | `desk_errors.time_s` |
| `lastErrors[].errorCode` | `desk_errors.error_code` |

## Python Persistence Integration

The persistence module should implement `save_desk(desk_record)` using the agreed Sprint 1 data contract.

Expected internal record structure:

```json
{
  "desk_id": "cd:fb:1a:53:fb:e6",
  "config": {
    "name": "DESK 4486",
    "manufacturer": "Desk-O-Matic Co."
  },
  "state": {
    "position_mm": 1100,
    "speed_mms": 0,
    "status": "Normal",
    "isPositionLost": false,
    "isOverloadProtectionUp": false,
    "isOverloadProtectionDown": false,
    "isAntiCollision": false
  },
  "usage": {
    "activationsCounter": 67,
    "sitStandCounter": 18
  },
  "lastErrors": [
    {
      "time_s": 2695,
      "errorCode": 93
    }
  ]
}
```

Recommended saving process:

1. Insert the desk into `desk`, or update its name and manufacturer if `desk_id` already exists. PostgreSQL `INSERT ... ON CONFLICT (desk_id) DO UPDATE` can be used.
2. Insert a new row into `desk_readings` using the desk's current state and usage counters.
3. Get the generated `reading_id` using `RETURNING reading_id`.
4. Insert each item from `lastErrors` into `desk_errors`, using the new `reading_id` and its array index as `error_index`.
5. Commit all inserts together in one transaction. Roll back if any operation fails.

If `lastErrors` is empty, no error rows need to be inserted.

Do not insert `reading_id`, `error_id`, `command_id`, `recorded_at`, or `requested_at` manually. PostgreSQL generates these values.

The saver should preserve unknown status strings and error codes instead of assuming only the currently known values are possible.

The simulator's `lastErrors` data is a recent-error snapshot, not a guaranteed list of newly occurring errors.

## Database Setup

The project uses PostgreSQL with the following local configuration:

- Database: `group7_desksystem`
- Host: `localhost`
- Port: `5432`
- Connection environment variable: `DATABASE_URL`
- Schema file: `database/001_initial_schema.sql`

Each developer creates their own local database.

To set up the database:

1. Create `group7_desksystem` in PostgreSQL.
2. Open the database using pgAdmin 4.
3. Run `database/001_initial_schema.sql` once on the new database.
4. Verify that `desk`, `desk_readings`, `desk_errors`, and `desk_commands` exist.

The Python saver should read the PostgreSQL connection URL from the `DATABASE_URL` environment variable. Database credentials must not be committed to Git.

The existing Python application does not automatically save API data to PostgreSQL. This requires the persistence module and backend integration.

## Testing

The schema was created and tested locally using PostgreSQL 18 and pgAdmin 4.

Successful tests:

- Creating all four tables
- Inserting and reading desk information
- Inserting desk readings
- Rejecting readings with unknown desk IDs (Foreign Key)
- Rejecting negative activation counters (CHECK)
- Inserting reported errors
- Rejecting duplicate `(reading_id, error_index)` values (UNIQUE)
- Inserting movement commands

The schema has been tested directly using SQL. End-to-end testing with the Python persistence module is still required.