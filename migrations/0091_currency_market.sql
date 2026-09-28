-- Migration: 0091 - Currency exchange market + currency-priced resource trades
-- Date: 2026-09-27
--
-- Kurai's fuller national-currency proposal (the follow-up 0079 left out):
--   * nations can hold other nations' currencies (currency_holdings). Only
--     the issuer can redeem its currency for gold at the fixed 5:1 rate
--     (app_core/currency/services.py::redeem_currency only reads the
--     issuer's own stats.national_currency_balance); foreign holders can
--     only trade it or spend it.
--   * a gold-priced exchange for those currencies (currency_market_offers),
--     with escrow on creation and refund on cancel. gold_escrow holds the
--     exact whole gold taken from a buy offer so partial fills + the final
--     refund always add back up to what was escrowed (no rounding mint).
--   * resource market offers and direct trades can be priced in a nation's
--     currency instead of gold (offers.currency_id / trades.currency_id,
--     NULL = gold, unchanged default). Plain integer, no FK: an FK with
--     CASCADE would delete escrowed offers when a nation is deleted and SET
--     NULL would turn a currency escrow into a gold refund; the code checks
--     the issuer still exists when settling instead.
-- Only users(id) FKs with CASCADE on the new tables: a deleted nation's
-- currency simply stops existing.

BEGIN;

CREATE TABLE IF NOT EXISTS currency_holdings (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    issuer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount NUMERIC(18,2) NOT NULL DEFAULT 0 CHECK (amount >= 0),
    PRIMARY KEY (user_id, issuer_id),
    CONSTRAINT currency_holdings_not_own CHECK (user_id <> issuer_id)
);
CREATE INDEX IF NOT EXISTS idx_currency_holdings_issuer ON currency_holdings (issuer_id);

CREATE TABLE IF NOT EXISTS currency_market_offers (
    offer_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    issuer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK (type IN ('buy', 'sell')),
    amount NUMERIC(18,2) NOT NULL CHECK (amount > 0),
    price_gold NUMERIC(12,2) NOT NULL CHECK (price_gold > 0),
    gold_escrow BIGINT NOT NULL DEFAULT 0 CHECK (gold_escrow >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_currency_market_offers_issuer
    ON currency_market_offers (issuer_id, type, price_gold);
CREATE INDEX IF NOT EXISTS idx_currency_market_offers_user
    ON currency_market_offers (user_id);

CREATE TABLE IF NOT EXISTS currency_market_trades (
    id SERIAL PRIMARY KEY,
    issuer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    buyer_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    seller_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    amount NUMERIC(18,2) NOT NULL,
    price_gold NUMERIC(12,2) NOT NULL,
    gold_total BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_currency_market_trades_issuer
    ON currency_market_trades (issuer_id, created_at DESC);

ALTER TABLE offers ADD COLUMN IF NOT EXISTS currency_id INTEGER;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS currency_id INTEGER;

COMMIT;
