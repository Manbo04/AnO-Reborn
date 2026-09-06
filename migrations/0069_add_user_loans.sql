-- Migration: 0069 - National loans (national debt mechanic)
-- Date: 2026-09-07
--
-- The economy currently has no downside to running out of gold -- tax
-- income and resource production only ever add to a nation's balance, with
-- no borrowing/interest system giving that a real risk/reward counterpart.
-- This adds a single-active-loan-per-nation borrowing mechanic: a nation
-- can borrow against its own population-scaled capacity, and interest is
-- garnished directly from its gold balance every hour (see
-- app_core/game_ticks/loan_interest.py) until repaid -- unlike a "test a
-- form" style feature, ignoring debt has a real, felt cost instead of
-- being free money.

BEGIN;

CREATE TABLE IF NOT EXISTS user_loans (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    principal NUMERIC NOT NULL,
    balance NUMERIC NOT NULL,
    interest_rate NUMERIC NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    taken_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    repaid_at TIMESTAMPTZ
);

-- Enforce "one active loan per nation" at the DB level, not just in the
-- service layer -- a partial unique index only covers status='active' rows,
-- so a repaid/cleared loan never blocks taking a new one.
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_loans_one_active
    ON user_loans (user_id) WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_user_loans_user_id ON user_loans (user_id);

COMMENT ON TABLE user_loans IS
    'National debt: a nation borrows gold against its population-scaled loan capacity (app_core/loans/services.py::compute_loan_cap). Interest is garnished from stats.gold every hour by app_core/game_ticks/loan_interest.py; any shortfall compounds into balance rather than being forgiven.';

COMMIT;
