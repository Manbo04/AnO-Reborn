-- Migration: 0073 - Nation customization/larp fields
-- Date: 2026-09-08
--
-- Discord (#suggestions "Some suggestions for country customisation/larp",
-- Cheesar, 2026-08-31/09-05): leader name, national currency name, and
-- ruling party are simple cosmetic text fields on the lore page. Also adds
-- province-level is_capital (a nation designates one province as its
-- capital) and flag_data (per-province flag image, same base64-in-DB
-- pattern as users.flag_data / colNames.flag_data -- see serve_flag() in
-- app_core/main/routes.py). Bulletins/news feed and military ensigns from
-- the same thread are bigger/out-of-scope items, tracked separately.

BEGIN;

ALTER TABLE users ADD COLUMN IF NOT EXISTS leader_name VARCHAR(60);
ALTER TABLE users ADD COLUMN IF NOT EXISTS currency_name VARCHAR(40);
ALTER TABLE users ADD COLUMN IF NOT EXISTS ruling_party VARCHAR(60);

ALTER TABLE provinces ADD COLUMN IF NOT EXISTS is_capital BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE provinces ADD COLUMN IF NOT EXISTS flag_data TEXT;

-- At most one capital per nation.
CREATE UNIQUE INDEX IF NOT EXISTS idx_provinces_one_capital_per_user
    ON provinces (userid) WHERE is_capital;

COMMIT;
