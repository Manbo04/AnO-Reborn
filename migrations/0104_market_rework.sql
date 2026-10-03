-- 0104_market_rework.sql
-- Discord #suggestions "Market UI Rework" (Helios/andy8583, 2026-10-03).
--
--   * market_preferences: per-nation market settings -- default resource the
--     order book opens on, and which offers to hide (currencies you can't get,
--     currencies only buyable on the Currency Exchange, embargo partners,
--     gold-only / single-currency mode).
--   * market_fills: one row per filled market offer (buy_offer / sell_offer).
--     trade_events only ever logged direct trades, so there was no "last
--     traded price" for market resources. gold_price is the price per unit
--     converted at the fixed national-currency rate (variables.CURRENCY_GOLD_PER_UNIT)
--     so fills in different currencies are comparable.
--   * market_auto_orders + market_auto_order_log: standing buy/sell rules the
--     hourly tick (app_core/game_ticks/market_auto_orders.py) tops up into one
--     managed offer per rule. All limits are optional but at least one of
--     max_offer / max_per_day must be set so a rule can never dump a whole
--     stockpile in one go. reserve_limit means "keep at least this much" for
--     sell rules and "stop once I hold this much" for buy rules.
--     currency_id NULL = gold, no FK -- same convention as offers.currency_id.

BEGIN;

CREATE TABLE IF NOT EXISTS market_preferences (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    default_resource TEXT,
    hide_unavailable BOOLEAN NOT NULL DEFAULT FALSE,
    hide_exchange BOOLEAN NOT NULL DEFAULT FALSE,
    hide_embargoed BOOLEAN NOT NULL DEFAULT TRUE,
    currency_mode TEXT NOT NULL DEFAULT 'all'
        CHECK (currency_mode IN ('all', 'gold', 'currency')),
    currency_id INTEGER,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS market_fills (
    id SERIAL PRIMARY KEY,
    offer_id INTEGER NOT NULL,
    resource TEXT NOT NULL,
    amount BIGINT NOT NULL,
    price INTEGER NOT NULL,
    currency_id INTEGER,
    gold_price INTEGER NOT NULL,
    seller_id INTEGER,
    buyer_id INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_market_fills_resource_time
    ON market_fills (resource, created_at DESC);

CREATE TABLE IF NOT EXISTS market_auto_orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK (type IN ('buy', 'sell')),
    resource TEXT NOT NULL,
    price INTEGER NOT NULL CHECK (price > 0),
    currency_id INTEGER,
    reserve_limit BIGINT CHECK (reserve_limit >= 0),
    max_offer BIGINT CHECK (max_offer > 0),
    max_per_day BIGINT CHECK (max_per_day > 0),
    alert_pct INTEGER CHECK (alert_pct BETWEEN 1 AND 1000),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    offer_id INTEGER,
    last_run_at TIMESTAMPTZ,
    last_status TEXT,
    last_alert_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, type, resource),
    CHECK (max_offer IS NOT NULL OR max_per_day IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_market_auto_orders_active
    ON market_auto_orders (id) WHERE active;

CREATE TABLE IF NOT EXISTS market_auto_order_log (
    id SERIAL PRIMARY KEY,
    auto_order_id INTEGER NOT NULL REFERENCES market_auto_orders(id) ON DELETE CASCADE,
    units BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_market_auto_order_log_rule_time
    ON market_auto_order_log (auto_order_id, created_at);

COMMIT;
