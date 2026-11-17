--Sprint 5: cleaning schedules and exuction history

--1. Store cleaning schedule settings
CREATE TABLE cleaning_schedules (
    schedule_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL,

    cleaning_height_mm INTEGER NOT NULL
        CHECK (cleaning_height_mm BETWEEN 680 AND 1320),

    return_height_mm INTEGER NOT NULL
        CHECK (return_height_mm BETWEEN 680 AND 1320),

    start_time TIME NOT NULL,
    end_time TIME NOT NULL,

    timezone TEXT NOT NULL DEFAULT 'Europe/Copenhagen',
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (start_time <> end_time)
    );

    --2. Connect schedules with their selected desks
    CREATE TABLE cleaning_schedule_desks (
    schedule_id BIGINT NOT NULL
        REFERENCES cleaning_schedules(schedule_id) ON DELETE CASCADE,

    desk_id TEXT NOT NULL
        REFERENCES desk(desk_id),

    PRIMARY KEY (schedule_id, desk_id)
    );

--3. Record each execution of a cleaning schedule
CREATE TABLE cleaning_runs(
    run_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    schedule_id BIGINT NOT NULL
        REFERENCES cleaning_schedules(schedule_id),

    occurrence_date DATE NOT NULL,
    status TEXT NOT NULL DEFAULT 'scheduled',

    raise_operation_id TEXT,
    return_operation_id TEXT,

    raise_requested_at TIMESTAMPTZ,
    return_requested_at TIMESTAMPTZ,

    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (schedule_id, occurrence_date),

    CHECK (status IN ('scheduled', 'raising', 'cleaning', 'returning', 'completed', 'cancelled', 'blocked', 'needs_review'))
);