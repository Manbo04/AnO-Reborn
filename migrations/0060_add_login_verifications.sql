-- Migration: 0060 - New-location login verification
-- Date: 2026-09-03
-- Following the Discord-login account-takeover incident (silent email-based
-- account merge, fixed separately), logins from an IP never seen before for
-- that account now have to be confirmed via a single-use link sent to the
-- account's linked Discord DM or verified email, instead of completing
-- immediately. This table holds those pending confirmations.

BEGIN;

CREATE TABLE IF NOT EXISTS login_verifications (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token VARCHAR(64) NOT NULL UNIQUE,
    ip VARCHAR(45),
    fingerprint TEXT,
    auth_type VARCHAR(20),
    delivery_method VARCHAR(20),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_login_verifications_user_id ON login_verifications(user_id);

COMMIT;
