-- Migration: 0078 - Store: add "Molten Forge" background cosmetic
-- Date: 2026-09-16
-- Player request (ticket-0032, germanicusjuliuscaesar / "Terra Homeworld"):
-- "a different background to my flag... fire like a forge dripping down the
-- screen." Priced/ordered above Deep Ocean Trench (550) given the added
-- CSS animation, in line with the more elaborate existing gradients.

BEGIN;

INSERT INTO cosmetics (slug, name, cosmetic_type, price_gems, css_class, is_active, sort_order)
VALUES
    ('molten-forge', 'Molten Forge', 'background', 650, 'bg-molten-forge', TRUE, 12)
ON CONFLICT DO NOTHING;

COMMIT;
