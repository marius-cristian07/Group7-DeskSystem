-- S4-2: Speed up reading historical desk data
-- Keep the existing tables and stored records unchanged

CREATE INDEX IF NOT EXISTS idx_desk_readings_history
ON desk_readings (desk_id, recorded_at DESC, reading_id DESC);

CREATE INDEX IF NOT EXISTS idx_desk_commands_history
ON desk_commands (desk_id, requested_at DESC, command_id DESC);