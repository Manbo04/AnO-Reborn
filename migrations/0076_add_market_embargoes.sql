-- Migration: 0076 - Market embargoes
-- Date: 2026-09-10
--
-- Player-requested feature (Discord #suggestions, Cheesar): let a nation block
-- specific nations from buying its goods on the public market. One row per
-- (embargoer, embargoed) pair; enforced in app_core/market/routes.py's
-- buy_market_offer/sell_market_offer against the offer owner's embargo list.

BEGIN;

CREATE TABLE IF NOT EXISTS market_embargoes (
    embargoer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    embargoed_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (embargoer_id, embargoed_id),
    CHECK (embargoer_id <> embargoed_id)
);

CREATE INDEX IF NOT EXISTS idx_market_embargoes_embargoed ON market_embargoes(embargoed_id);

COMMENT ON TABLE market_embargoes IS
    'A nation (embargoer_id) refuses to sell to / buy from another (embargoed_id) via public market offers. Checked in app_core/market/routes.py buy_market_offer and sell_market_offer.';

COMMIT;
