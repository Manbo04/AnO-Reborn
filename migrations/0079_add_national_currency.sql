-- Migration: 0079 - Functional national currency (central bank)
-- Date: 2026-09-22
--
-- Discord #suggestions (Kurai, 2026-09-16, "national currency"): instead of
-- every nation just using gold, each nation can convert its own tax revenue
-- into its own currency at a fixed exchange rate. The existing
-- users.currency_name column (migration 0073) is purely cosmetic/larp text
-- with no functional effect -- this adds the actual tracked balance and
-- conversion mechanic behind it, reusing currency_name as the display name
-- rather than creating a second competing "currency name" concept.
--
-- Rate is a single fixed global constant (variables.CURRENCY_GOLD_PER_UNIT,
-- currently 5 gold per 1 unit, matching Kurai's proposed rate) rather than
-- player-adjustable -- a truly fixed, never-changing rate makes minting and
-- redeeming exactly value-neutral (5 gold -> 1 currency -> 5 gold nets to
-- zero, always), so there is no window where changing a rate between two
-- conversions would let anyone create gold from nothing. Kurai's fuller
-- proposal (player-driven/market exchange rates, spending currency on
-- resource trades with other nations, Assembly-of-Nations supply laws) is
-- a much larger P2P market feature layered on top of this -- out of scope
-- for this pass, left for follow-up.

BEGIN;

ALTER TABLE stats ADD COLUMN IF NOT EXISTS national_currency_balance NUMERIC(18,2) NOT NULL DEFAULT 0;

COMMENT ON COLUMN stats.national_currency_balance IS
    'Functional per-nation currency balance, minted from / redeemed for stats.gold at the fixed rate in variables.CURRENCY_GOLD_PER_UNIT (app_core/currency/services.py). Display name is users.currency_name (cosmetic field, migration 0073).';

-- Audit ledger, not required for the mechanic itself but cheap to add and
-- useful if a balance ever looks wrong -- every conversion (either
-- direction) gets one row.
CREATE TABLE IF NOT EXISTS national_currency_conversions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    direction TEXT NOT NULL, -- 'mint' (gold -> currency) or 'redeem' (currency -> gold)
    gold_amount NUMERIC(18,2) NOT NULL,
    currency_amount NUMERIC(18,2) NOT NULL,
    rate NUMERIC(18,2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_national_currency_conversions_user_id
    ON national_currency_conversions (user_id);

COMMIT;
