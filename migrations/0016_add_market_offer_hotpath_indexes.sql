-- Migration 0016: Add hot-path indexes for legacy offers/trades tables
-- These indexes support /market filtering, sorting and pagination paths.

CREATE INDEX IF NOT EXISTS idx_offers_type_resource_price_offerid
ON offers(type, resource, price, offer_id);

CREATE INDEX IF NOT EXISTS idx_offers_resource_type_price_offerid
ON offers(resource, type, price, offer_id);

CREATE INDEX IF NOT EXISTS idx_offers_user_id_offer_id
ON offers(user_id, offer_id);

CREATE INDEX IF NOT EXISTS idx_trades_offer_id
ON trades(offer_id);

CREATE INDEX IF NOT EXISTS idx_trades_offerer_offer_id
ON trades(offerer, offer_id);

CREATE INDEX IF NOT EXISTS idx_trades_offeree_offer_id
ON trades(offeree, offer_id);
