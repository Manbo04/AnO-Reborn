-- Migration: 0045 - Track login-time IP + fingerprint
-- Date: 2026-08-23
-- signup_attempts already logs ip/fingerprint for signups (rate limiting), but
-- nothing equivalent exists for actual logins, so there was no way to check
-- "did these two accounts ever log in from the same IP/device" after the fact.
-- This was surfaced while investigating a multi-account report in the
-- Leviathan coalition (see 0044 for the same reporter, "Unknown Identity").

BEGIN;

CREATE TABLE IF NOT EXISTS login_events (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ip VARCHAR(45),
    fingerprint TEXT,
    auth_type VARCHAR(20),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_login_events_user_id ON login_events(user_id);
CREATE INDEX IF NOT EXISTS idx_login_events_ip ON login_events(ip);

COMMIT;
