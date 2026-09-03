-- Migration: 0061 - Store: expand cosmetics to name_color/badge/title/country_border
-- Date: 2026-09-03
-- Adds the schema for 4 new cosmetic types (name flair shown next to a
-- nation's name everywhere it appears, and a country-page border accent),
-- on top of the background-only catalog from 0048. See app_core/store/ and
-- the render_nation_name macro in templates/macros/game_ui.html.

BEGIN;

-- Generic per-type payload: hex color for name_color, Material Icons
-- ligature name for badge. NULL for background/title/country_border
-- (those use css_class and/or name instead -- see plan).
ALTER TABLE cosmetics
    ADD COLUMN IF NOT EXISTS value TEXT;

-- name_color and title items have no css_class (name_color is applied via
-- inline style from `value`; title has nothing to style at all) -- was
-- NOT NULL from the original background-only schema (0048).
ALTER TABLE cosmetics
    ALTER COLUMN css_class DROP NOT NULL;

ALTER TABLE cosmetics DROP CONSTRAINT IF EXISTS cosmetics_cosmetic_type_check;
ALTER TABLE cosmetics
    ADD CONSTRAINT cosmetics_cosmetic_type_check
        CHECK (cosmetic_type IN ('background', 'name_color', 'badge', 'title', 'country_border'));

-- One equip slot per new type, same ON DELETE SET NULL posture as the
-- existing equipped_background_cosmetic_id (retiring a catalog item
-- silently falls the player back to "nothing equipped").
ALTER TABLE stats
    ADD COLUMN IF NOT EXISTS equipped_name_color_cosmetic_id BIGINT
        REFERENCES cosmetics(id) ON DELETE SET NULL;
ALTER TABLE stats
    ADD COLUMN IF NOT EXISTS equipped_badge_cosmetic_id BIGINT
        REFERENCES cosmetics(id) ON DELETE SET NULL;
ALTER TABLE stats
    ADD COLUMN IF NOT EXISTS equipped_title_cosmetic_id BIGINT
        REFERENCES cosmetics(id) ON DELETE SET NULL;
ALTER TABLE stats
    ADD COLUMN IF NOT EXISTS equipped_country_border_cosmetic_id BIGINT
        REFERENCES cosmetics(id) ON DELETE SET NULL;

COMMIT;
