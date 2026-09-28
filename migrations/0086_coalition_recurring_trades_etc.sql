-- Migration: 0086 - Recurring coalition bank trades, bank-log trade tagging,
-- loan credit-score history
-- Date: 2026-09-27
--
-- 1. col_bank_transactions.kind: 'trade' for the two legs of a bank trade
--    (one-off or recurring), 'manual' for everything else. Lets the Discord
--    /bank-summary command (Kurai) tell trades apart from plain deposits and
--    withdrawals. Tax rows keep resource='tax' as before. The table itself is
--    created at app start by database.py (ensure_schema_compat), so only
--    alter it when it already exists; database.py adds the column too.
-- 2. col_bank_recurring_trades (+ history): a member's standing bank trade
--    ("give 5,000 steel, get 2,000,000 money, every 24h, 10 times"), approved
--    once by a leader/deputy/banker and then executed by
--    app_core/game_ticks/recurring_bank_trades.py. Each occurrence has a
--    unique (recurring_trade_id, scheduled_for) history row, so the same
--    occurrence can never be executed twice even if two ticks overlap.
-- 3. user_loans.cap_at_take: borrowing cap when a loan was taken, so the
--    loan credit score can tell a real loan from a token one
--    (app_core/loans/services.py::score_loan_history).

BEGIN;

DO $$
BEGIN
    IF to_regclass('public.col_bank_transactions') IS NOT NULL THEN
        ALTER TABLE col_bank_transactions
            ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'manual';
    END IF;
END $$;

ALTER TABLE user_loans ADD COLUMN IF NOT EXISTS cap_at_take BIGINT;

CREATE TABLE IF NOT EXISTS col_bank_recurring_trades (
    id SERIAL PRIMARY KEY,
    coalition_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    give_resource TEXT NOT NULL,
    give_amount BIGINT NOT NULL CHECK (give_amount > 0),
    want_resource TEXT NOT NULL,
    want_amount BIGINT NOT NULL CHECK (want_amount > 0),
    interval_hours INTEGER NOT NULL CHECK (interval_hours > 0),
    max_repetitions INTEGER CHECK (max_repetitions IS NULL OR max_repetitions > 0), -- NULL = until cancelled
    repetitions_done INTEGER NOT NULL DEFAULT 0,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    approved_at TIMESTAMPTZ,
    approved_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    next_execution_at TIMESTAMPTZ,
    last_executed_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    ended_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT col_bank_recurring_trades_status_check
        CHECK (status IN ('pending', 'active', 'paused', 'completed', 'cancelled', 'declined')),
    CONSTRAINT col_bank_recurring_trades_distinct_resources CHECK (give_resource <> want_resource)
);

CREATE INDEX IF NOT EXISTS idx_col_bank_recurring_trades_due
    ON col_bank_recurring_trades (next_execution_at) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_col_bank_recurring_trades_coalition
    ON col_bank_recurring_trades (coalition_id, status);
CREATE INDEX IF NOT EXISTS idx_col_bank_recurring_trades_user
    ON col_bank_recurring_trades (user_id);

CREATE TABLE IF NOT EXISTS col_bank_recurring_trade_runs (
    id BIGSERIAL PRIMARY KEY,
    recurring_trade_id INTEGER NOT NULL REFERENCES col_bank_recurring_trades(id) ON DELETE CASCADE,
    scheduled_for TIMESTAMPTZ NOT NULL,
    executed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    outcome TEXT NOT NULL,
    CONSTRAINT col_bank_recurring_trade_runs_outcome_check
        CHECK (outcome IN ('success', 'member_short', 'bank_short')),
    CONSTRAINT col_bank_recurring_trade_runs_once UNIQUE (recurring_trade_id, scheduled_for)
);
CREATE INDEX IF NOT EXISTS idx_col_bank_recurring_trade_runs_time
    ON col_bank_recurring_trade_runs (recurring_trade_id, executed_at DESC);

COMMIT;
