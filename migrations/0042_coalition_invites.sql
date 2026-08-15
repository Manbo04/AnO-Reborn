-- Migration 0042: Coalition invites
--
-- Backs a coalition leader/deputy send-invite flow that was built into
-- app_core/coalitions/routes.py (send/view/accept/reject/revoke) but never
-- got its own table -- every one of those routes threw UndefinedTable.

BEGIN;

CREATE TABLE IF NOT EXISTS coalition_invites (
    id SERIAL PRIMARY KEY,
    coalition_id INTEGER NOT NULL REFERENCES colNames(id),
    invited_user_id INTEGER NOT NULL REFERENCES users(id),
    invited_by_user_id INTEGER NOT NULL REFERENCES users(id),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_coalition_invites_invited_user
    ON coalition_invites (invited_user_id, status);
CREATE INDEX IF NOT EXISTS idx_coalition_invites_coalition
    ON coalition_invites (coalition_id, status);

COMMIT;
