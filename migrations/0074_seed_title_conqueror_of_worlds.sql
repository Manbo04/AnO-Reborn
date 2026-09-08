-- Migration: 0074 - Store: add "Conqueror of Worlds" title cosmetic
-- Date: 2026-09-08
-- Player request (Discord #general, Unknown Identity, 04/09): a step up
-- from the existing 'title-conqueror' (280 gems, sort_order 7). Priced and
-- ordered just above it in the same catalog from 0062.

BEGIN;

INSERT INTO cosmetics (slug, name, cosmetic_type, price_gems, is_active, sort_order)
VALUES
    ('title-conqueror-of-worlds', 'Conqueror of Worlds', 'title', 320, TRUE, 8)
ON CONFLICT DO NOTHING;

COMMIT;
