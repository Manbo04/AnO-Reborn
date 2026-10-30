-- Vacation mode: the player picks how long it lasts; it ends on its own at vacation_until.
ALTER TABLE users ADD COLUMN IF NOT EXISTS vacation_until TIMESTAMPTZ;
