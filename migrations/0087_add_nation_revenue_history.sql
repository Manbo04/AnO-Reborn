-- Migration: 0087 - Per-nation per-tick gold ledger (revenue history)
-- Date: 2026-09-27
--
-- Discord suggestion (2026-09-26 sweep): show how much gold a nation actually
-- made/spent over the last 24h / 7d / 30d, broken down by where it came from.
-- Nothing recorded this per tick before (the revenue tab only projects the
-- next hour). The hourly ticks (tax_income, generate_province_revenue) each
-- write ONE batched INSERT here per run; rows older than 30 days are pruned
-- by the tax tick. amount is signed: > 0 income, < 0 spending.

CREATE TABLE IF NOT EXISTS nation_revenue_history (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    category VARCHAR(32) NOT NULL,
    amount BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_nation_revenue_history_user_time
    ON nation_revenue_history (user_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_nation_revenue_history_time
    ON nation_revenue_history (recorded_at);
