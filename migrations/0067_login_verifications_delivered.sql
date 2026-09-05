-- Migration: 0067 - login_verifications.delivered + always-insert audit trail
-- Date: 2026-09-05
-- Following the reset_account account-takeover incident (2026-09-05, user
-- id=1's session compromised, self-service full reset used to hard-delete
-- provinces/military/buildings/wars with no recovery path), it became clear
-- start_login_verification() only ever INSERTed a login_verifications row
-- when the Discord DM/email alert was actually delivered. When delivery
-- silently failed (e.g. the Discord bot API errored out), there was zero
-- durable record that a new-location login even happened, so during the
-- incident nobody could tell whether the "secure your account" alert had
-- ever fired. This adds a `delivered` column so every new-location login
-- attempt gets a row, whether or not the alert was actually sent.

BEGIN;

ALTER TABLE login_verifications ADD COLUMN IF NOT EXISTS delivered BOOLEAN;

COMMENT ON COLUMN login_verifications.delivered IS
    'Whether the Discord DM/email alert for this new-location login was actually delivered. NULL for rows written before this column existed.';

COMMIT;
