-- Register new resources (silver, diamonds, bullion) and new buildings
-- (silver_mines, diamond_mines, bullion_mines, fisheries, workshops,
-- jewelry_stores, automotive_plants).

BEGIN;

-- 1. Insert new resources into resource_dictionary
INSERT INTO resource_dictionary
    (name, display_name, description, is_production, is_raw, is_active)
VALUES
    ('silver',   'Silver',   'Precious metal mined from mineral veins, used in jewelry and luxury goods.', false, true, true),
    ('diamonds', 'Diamonds', 'Precious gemstones mined from deep kimberlite pipes, used in jewelry and luxury goods.', false, true, true),
    ('bullion',  'Bullion',  'Refined gold bullion mined and cast into bars, highly prized for trade and jewelry.', false, true, true)
ON CONFLICT (name) DO NOTHING;

-- 2. Backfill user_economy rows for all users and the new resources
INSERT INTO user_economy (user_id, resource_id, quantity)
SELECT u.id, rd.resource_id, 0
FROM users u
CROSS JOIN resource_dictionary rd
WHERE rd.name IN ('silver', 'diamonds', 'bullion')
ON CONFLICT (user_id, resource_id) DO NOTHING;

-- 3. Insert new buildings into building_dictionary
-- Required NOT NULL columns: name, display_name, category, base_cost, effect_type, effect_value, maintenance_cost, description
INSERT INTO building_dictionary
    (name, display_name, category, base_cost, effect_type, effect_value, maintenance_cost, description)
VALUES
    ('silver_mines',     'Silver Mines',      'resource_production',   4000000, 'resource_production',  60.00,  12000, 'Extracts silver from mineral veins.'),
    ('diamond_mines',    'Diamond Mines',     'resource_production',   6000000, 'resource_production',  30.00,  25000, 'Mines diamonds from deep kimberlite pipes.'),
    ('bullion_mines',    'Bullion Mines',     'resource_production',   5000000, 'resource_production',  40.00,  18000, 'Mines and casts precious metal bullion.'),
    ('fisheries',        'Fisheries',         'resource_production',    800000, 'resource_production', 160.00,   1800, 'Aquaculture and coastal fisheries producing food rations.'),
    ('workshops',        'Workshops',         'commerce',              3000000, 'resource_production',   4.00,  12000, 'Artisan workshops crafting consumer goods from steel.'),
    ('jewelry_stores',   'Jewelry Stores',    'commerce',             45000000, 'resource_production',  36.00,  60000, 'High-end jewelry stores crafting luxury consumer goods from silver, diamonds, and bullion.'),
    ('automotive_plants','Automotive Plants', 'commerce',            350000000, 'resource_production', 160.00, 180000, 'Large-scale automotive manufacturing plants producing high volumes of consumer goods.')
ON CONFLICT (name) DO NOTHING;
-- 4. Add columns to spyinfo and colbanks for the new resources
ALTER TABLE spyinfo ADD COLUMN IF NOT EXISTS silver BIGINT DEFAULT 0;
ALTER TABLE spyinfo ADD COLUMN IF NOT EXISTS diamonds BIGINT DEFAULT 0;
ALTER TABLE spyinfo ADD COLUMN IF NOT EXISTS bullion BIGINT DEFAULT 0;

ALTER TABLE colbanks ADD COLUMN IF NOT EXISTS silver BIGINT DEFAULT 0;
ALTER TABLE colbanks ADD COLUMN IF NOT EXISTS diamonds BIGINT DEFAULT 0;
ALTER TABLE colbanks ADD COLUMN IF NOT EXISTS bullion BIGINT DEFAULT 0;

COMMIT;
