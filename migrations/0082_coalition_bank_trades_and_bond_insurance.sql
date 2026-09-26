-- Migration: 0082 - Coalition bank trade requests + coalition bond insurance
-- Date: 2026-09-27
--
-- Requested by Kurai in #suggestions ("Kurai suggestions" thread):
--  1. "Notify the banker whenever a member fails to pay back the bonds they
--     issued, and if possible add an 'insurance system' where the coalition
--     can choose which players can get their debts repaid to them in case of
--     a default" (2026-09-24).
--  2. "Set up an option to trade with the coalition bank through sending
--     automatic trades that can be approved by the banker" (2026-09-26).
--
-- Insurance: leadership marks members as insured. When an insured member's
-- bond defaults with a shortfall, app_core/game_ticks/bond_tick.py pays the
-- lender out of the coalition bank's money (as much as the bank holds), and
-- that covered amount becomes insurer_owed -- the defaulter now owes the
-- coalition bank instead of the lender, and the tick keeps garnishing it
-- into colBanks.money. Defaulting is still never free money; it just moves
-- who the defaulter owes.
--
-- Bank trades: a member proposes "I give X of A, the bank gives me Y of B".
-- The member's side is taken into escrow when they submit (so an accepted
-- trade can't come up short), a leader/deputy/banker accepts or declines,
-- and declining/cancelling refunds the escrow. See app_core/coalition_bank/.

BEGIN;

CREATE TABLE IF NOT EXISTS coalition_bond_insurance (
    coalition_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    added_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (coalition_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_coalition_bond_insurance_user ON coalition_bond_insurance (user_id);

ALTER TABLE bonds ADD COLUMN IF NOT EXISTS insurer_coalition_id INTEGER;
ALTER TABLE bonds ADD COLUMN IF NOT EXISTS insurer_owed NUMERIC NOT NULL DEFAULT 0;
ALTER TABLE bonds ADD COLUMN IF NOT EXISTS insurance_paid NUMERIC NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS col_bank_trades (
    id SERIAL PRIMARY KEY,
    coalition_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    give_resource TEXT NOT NULL,
    give_amount BIGINT NOT NULL CHECK (give_amount > 0),
    want_resource TEXT NOT NULL,
    want_amount BIGINT NOT NULL CHECK (want_amount > 0),
    note TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    resolved_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT col_bank_trades_status_check CHECK (status IN ('pending', 'accepted', 'declined', 'cancelled')),
    CONSTRAINT col_bank_trades_distinct_resources CHECK (give_resource <> want_resource)
);
CREATE INDEX IF NOT EXISTS idx_col_bank_trades_coalition_status ON col_bank_trades (coalition_id, status);
CREATE INDEX IF NOT EXISTS idx_col_bank_trades_user ON col_bank_trades (user_id);

COMMIT;
