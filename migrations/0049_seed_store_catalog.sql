-- Migration: 0049 - Store: seed starter catalog (Gem packages + cosmetics)
-- Date: 2026-08-26
-- Seeds a v1 starter catalog for the Store feature added in 0048. Draft
-- content only — prices/themes are a reasonable v1 pass, not final; review
-- before this ever goes live for real money. All cosmetics below are
-- CSS-only gradients (no image assets), matching the pattern documented at
-- the top of static/css/cosmetics.css.

BEGIN;

-- Gem packages: real-money tiers with a modest bulk discount on larger
-- tiers (300 gems/$ on the starter tier, ~350-400 gems/$ on the largest).
INSERT INTO gem_packages (name, gems_granted, price_cents, currency, is_active, sort_order)
VALUES
    ('Starter Pack', 300, 299, 'usd', TRUE, 0),
    ('Popular Pack', 550, 499, 'usd', TRUE, 1),
    ('Value Pack', 1200, 999, 'usd', TRUE, 2),
    ('Mega Pack', 2800, 1999, 'usd', TRUE, 3)
ON CONFLICT DO NOTHING;

-- Cosmetics: background gradients, priced to feel attainable relative to
-- the packages above (the cheapest is affordable from the Starter Pack
-- alone; the priciest needs roughly a Value Pack).
INSERT INTO cosmetics (slug, name, cosmetic_type, price_gems, css_class, is_active, sort_order)
VALUES
    ('sunset-horizon', 'Sunset Horizon', 'background', 150, 'bg-sunset-horizon', TRUE, 0),
    ('emerald-canopy', 'Emerald Canopy', 'background', 250, 'bg-emerald-canopy', TRUE, 1),
    ('aurora-borealis', 'Aurora Borealis', 'background', 500, 'bg-aurora-borealis', TRUE, 2),
    ('midnight-nebula', 'Midnight Nebula', 'background', 400, 'bg-midnight-nebula', TRUE, 3),
    ('neon-circuit', 'Neon Circuit', 'background', 600, 'bg-neon-circuit', TRUE, 4),
    ('royal-amethyst', 'Royal Amethyst', 'background', 900, 'bg-royal-amethyst', TRUE, 5)
ON CONFLICT DO NOTHING;

COMMIT;
