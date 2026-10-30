-- Vacation mode: protects a nation while its player is away (#suggestions vote 13-0).
-- Rules live in app_core/vacation.py (no wars to enable, 72h minimum, 7-day cooldown).
ALTER TABLE users ADD COLUMN IF NOT EXISTS vacation_mode BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS vacation_started_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS vacation_ended_at TIMESTAMPTZ;
