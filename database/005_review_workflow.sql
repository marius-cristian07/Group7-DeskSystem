-- S6-3: manager review and resolution of failed cleaning runs, group operations and desk incidents.
-- Apply after migrations 001-004. It only adds to the existing tables, nothing is dropped or rewritten.

-- 1. A cleaning run that a manager has reviewed gets its own final status, 'resolved'.
--    It is not 'completed': the desks may still need a separate, explicit movement.
ALTER TABLE cleaning_runs DROP CONSTRAINT IF EXISTS cleaning_runs_status_check;
ALTER TABLE cleaning_runs ADD CONSTRAINT cleaning_runs_status_check CHECK (
    status IN (
        'scheduled', 'raising', 'cleaning', 'returning', 'completed',
        'cancelled', 'blocked', 'needs_review', 'resolved'
    )
);

-- Why an automatic start was blocked, and when a manager reviewed the run.
ALTER TABLE cleaning_runs ADD COLUMN blocked_reason TEXT;
ALTER TABLE cleaning_runs ADD COLUMN reviewed_at TIMESTAMPTZ;

-- 2. "I have seen this fault" is not "this fault is cleared". Acknowledging only sets this time.
--    It changes neither review_state nor cleared_at and never unblocks anything.
ALTER TABLE desk_incidents ADD COLUMN acknowledged_at TIMESTAMPTZ;

-- 3. One record for every acknowledgement and every resolution: who, when, what was decided
--    and why. Rows are only ever added.
CREATE TABLE review_records (
    record_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    subject_type TEXT NOT NULL
        CHECK (subject_type IN ('cleaning_run', 'group_operation', 'desk_incident')),
    subject_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('acknowledged', 'resolved')),
    decision TEXT,
    explanation TEXT NOT NULL,
    recorded_by TEXT,
    desk_checks JSONB,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (action <> 'resolved' OR decision IS NOT NULL)
);

CREATE INDEX idx_review_records_subject
ON review_records (subject_type, subject_id, record_id DESC);
