-- Initial PostgreSQL schema; run once in the project database as described in database/SETUP.md.
-- desk holds identities; desk_readings and desk_commands hold history for those desks.
-- desk_errors belongs to a reading, so an old snapshot keeps its own error list.

-- One row per desk, shared by its readings and movement requests.
CREATE TABLE desk (
    desk_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    manufacturer TEXT NOT NULL
    );
-- Each sync adds a snapshot; older readings remain available as history.
CREATE TABLE desk_readings (
    reading_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    desk_id TEXT NOT NULL REFERENCES desk(desk_id),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    position_mm INTEGER NOT NULL,
    speed_mms INTEGER NOT NULL,
    status TEXT NOT NULL,
    activations_counter INTEGER NOT NULL CHECK (activations_counter >= 0),
    sit_stand_counter INTEGER NOT NULL CHECK (sit_stand_counter >= 0),
    is_position_lost BOOLEAN NOT NULL,
    is_overload_protection_up BOOLEAN NOT NULL,
    is_overload_protection_down BOOLEAN NOT NULL,
    is_anti_collision BOOLEAN NOT NULL
    );
-- Errors belong to a specific reading, with their original list order.
CREATE TABLE desk_errors (
    error_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    reading_id BIGINT NOT NULL REFERENCES desk_readings(reading_id),
    error_index INTEGER NOT NULL CHECK (error_index >= 0),
    time_s INTEGER NOT NULL CHECK (time_s >= 0),
    error_code INTEGER NOT NULL CHECK (error_code >= 0),
    UNIQUE (reading_id, error_index)
    );
-- Store requested targets; acceptance does not mean movement is complete.
CREATE TABLE desk_commands(
    desk_id TEXT NOT NULL REFERENCES desk(desk_id),
    command_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    target_position_mm INTEGER NOT NULL CHECK (target_position_mm > 0),
    status TEXT NOT NULL
);
