-- S6-2: Persistent group operations and desk incidents.

-- 1. Group operations
CREATE TABLE group_operations (
    operation_id TEXT PRIMARY KEY,
    reason TEXT NOT NULL,
    target_position_mm INTEGER NOT NULL
        CHECK (target_position_mm BETWEEN 680 AND 1320),
    state TEXT NOT NULL CHECK (state IN (
        'pending_warning', 'countdown', 'dispatching', 'monitoring',
        'completed', 'partial_failure', 'failed', 'cancelled', 'blocked',
        'interrupted'
    )),
    required_channels TEXT[] NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    dispatched_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    blocked_code TEXT,
    blocked_message TEXT,
    review_state TEXT NOT NULL DEFAULT 'not_required'
        CHECK (review_state IN ('not_required', 'needs_review', 'resolved')),
    reviewed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_group_operations_history
ON group_operations (created_at DESC, operation_id DESC);


-- 2. Individual desk results
CREATE TABLE group_operation_desks (
    operation_id TEXT NOT NULL
        REFERENCES group_operations(operation_id) ON DELETE CASCADE,
    desk_id TEXT NOT NULL,
    result TEXT NOT NULL,
    detail TEXT NOT NULL,
    dispatch_intent_at TIMESTAMPTZ,
    command_id BIGINT REFERENCES desk_commands(command_id),
    command_status TEXT,
    accepted_position_mm INTEGER,
    last_position_mm INTEGER,
    last_speed_mms INTEGER,
    last_status TEXT,
    last_observed_at TIMESTAMPTZ,
    fault_codes TEXT[] NOT NULL DEFAULT '{}',
    at_target BOOLEAN,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (operation_id, desk_id)
);


-- 3. Persistent desk incidents
CREATE TABLE desk_incidents (
    incident_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    desk_id TEXT NOT NULL REFERENCES desk(desk_id),
    fault_category TEXT NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    first_reading_id BIGINT NOT NULL REFERENCES desk_readings(reading_id),
    last_reading_id BIGINT NOT NULL REFERENCES desk_readings(reading_id),
    observation_count INTEGER NOT NULL DEFAULT 1 CHECK (observation_count > 0),
    cleared_at TIMESTAMPTZ,
    operation_id TEXT REFERENCES group_operations(operation_id),
    review_state TEXT NOT NULL DEFAULT 'needs_review'
        CHECK (review_state IN ('needs_review', 'resolved')),
    reviewed_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX uq_desk_incidents_open
ON desk_incidents (desk_id, fault_category)
WHERE cleared_at IS NULL;

CREATE INDEX idx_desk_incidents_history
ON desk_incidents (desk_id, first_seen_at DESC);