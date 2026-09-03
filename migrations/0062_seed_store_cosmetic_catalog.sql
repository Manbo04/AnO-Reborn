-- Migration: 0062 - Store: seed name_color/badge/title/country_border + more backgrounds
-- Date: 2026-09-03
-- Draft v1 catalog for the cosmetic types added in 0061, plus 6 more
-- backgrounds (Dede: "way more things buyable with gems"). Review pricing
-- before this ever goes live for real money (FEATURE_STORE is off).

BEGIN;

-- 6 more background gradients (on top of the 6 from 0049).
INSERT INTO cosmetics (slug, name, cosmetic_type, price_gems, css_class, is_active, sort_order)
VALUES
    ('crimson-wasteland', 'Crimson Wasteland', 'background', 200, 'bg-crimson-wasteland', TRUE, 6),
    ('golden-savanna', 'Golden Savanna', 'background', 200, 'bg-golden-savanna', TRUE, 7),
    ('arctic-frost', 'Arctic Frost', 'background', 350, 'bg-arctic-frost', TRUE, 8),
    ('volcanic-ember', 'Volcanic Ember', 'background', 450, 'bg-volcanic-ember', TRUE, 9),
    ('deep-ocean-trench', 'Deep Ocean Trench', 'background', 550, 'bg-deep-ocean-trench', TRUE, 10),
    ('cherry-blossom-dusk', 'Cherry Blossom Dusk', 'background', 700, 'bg-cherry-blossom-dusk', TRUE, 11)
ON CONFLICT DO NOTHING;

-- Name colors: hex applied inline via render_nation_name, no CSS file edit needed.
INSERT INTO cosmetics (slug, name, cosmetic_type, price_gems, value, is_active, sort_order)
VALUES
    ('name-crimson-blaze', 'Crimson Blaze', 'name_color', 120, '#e63946', TRUE, 0),
    ('name-sunflower-gold', 'Sunflower Gold', 'name_color', 120, '#f2a900', TRUE, 1),
    ('name-emerald-green', 'Emerald Green', 'name_color', 120, '#2ea043', TRUE, 2),
    ('name-sky-cyan', 'Sky Cyan', 'name_color', 150, '#00b4d8', TRUE, 3),
    ('name-royal-purple', 'Royal Purple', 'name_color', 150, '#8e44ad', TRUE, 4),
    ('name-hot-pink', 'Hot Pink', 'name_color', 180, '#ff4d94', TRUE, 5),
    ('name-tangerine', 'Tangerine', 'name_color', 180, '#ff8c42', TRUE, 6),
    ('name-deep-rose', 'Deep Rose', 'name_color', 220, '#d6336c', TRUE, 7)
ON CONFLICT DO NOTHING;

-- Badges: value = Material Icons Outlined ligature (matches the icon set
-- already used sitewide by game_button/game_panel).
INSERT INTO cosmetics (slug, name, cosmetic_type, price_gems, value, is_active, sort_order)
VALUES
    ('badge-rising-star', 'Rising Star', 'badge', 150, 'stars', TRUE, 0),
    ('badge-iron-shield', 'Iron Shield', 'badge', 180, 'shield', TRUE, 1),
    ('badge-diplomat', 'Diplomat', 'badge', 180, 'handshake', TRUE, 2),
    ('badge-veteran-commander', 'Veteran Commander', 'badge', 220, 'military_tech', TRUE, 3),
    ('badge-warmonger', 'Warmonger', 'badge', 220, 'local_fire_department', TRUE, 4),
    ('badge-elite-council', 'Elite Council', 'badge', 280, 'workspace_premium', TRUE, 5),
    ('badge-champion', 'Champion', 'badge', 320, 'emoji_events', TRUE, 6),
    ('badge-verified-legend', 'Verified Legend', 'badge', 400, 'verified', TRUE, 7)
ON CONFLICT DO NOTHING;

-- Titles: name IS the display text shown next to the nation's name.
INSERT INTO cosmetics (slug, name, cosmetic_type, price_gems, is_active, sort_order)
VALUES
    ('title-the-benevolent', 'The Benevolent', 'title', 150, TRUE, 0),
    ('title-the-diplomat', 'The Diplomat', 'title', 150, TRUE, 1),
    ('title-the-unyielding', 'The Unyielding', 'title', 180, TRUE, 2),
    ('title-iron-fist', 'Iron Fist', 'title', 180, TRUE, 3),
    ('title-warlord', 'Warlord', 'title', 200, TRUE, 4),
    ('title-the-visionary', 'The Visionary', 'title', 200, TRUE, 5),
    ('title-architect-of-empires', 'Architect of Empires', 'title', 250, TRUE, 6),
    ('title-conqueror', 'Conqueror', 'title', 280, TRUE, 7)
ON CONFLICT DO NOTHING;

-- Country borders: css_class -> a border/box-shadow rule in cosmetics.css.
INSERT INTO cosmetics (slug, name, cosmetic_type, price_gems, css_class, is_active, sort_order)
VALUES
    ('border-golden-crest', 'Golden Crest', 'country_border', 250, 'border-golden-crest', TRUE, 0),
    ('border-obsidian-frame', 'Obsidian Frame', 'country_border', 250, 'border-obsidian-frame', TRUE, 1),
    ('border-emerald-laurel', 'Emerald Laurel', 'country_border', 300, 'border-emerald-laurel', TRUE, 2),
    ('border-royal-crimson', 'Royal Crimson Trim', 'country_border', 300, 'border-royal-crimson', TRUE, 3),
    ('border-frostbound-edge', 'Frostbound Edge', 'country_border', 350, 'border-frostbound-edge', TRUE, 4),
    ('border-molten-core', 'Molten Core Rim', 'country_border', 400, 'border-molten-core', TRUE, 5)
ON CONFLICT DO NOTHING;

COMMIT;
