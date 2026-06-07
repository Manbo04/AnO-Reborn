-- Backup recovery key for password reset when email/Discord unavailable.
ALTER TABLE users ADD COLUMN IF NOT EXISTS recovery_key VARCHAR(255);
