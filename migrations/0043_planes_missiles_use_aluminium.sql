-- Migration: 0043 - Planes and missiles/nukes consume aluminium instead of steel
-- Date: 2026-08-17
-- Player feedback (germanicusjuliuscaesar, #military-recommendations): planes
-- are built from aluminium in reality, not steel, and steel had become the
-- dominant resource with aluminium barely used outside food-distribution
-- buildings. Dede agreed in-thread. Moving fighters/bombers/apaches and the
-- warhead-delivery units (icbms/nukes) from steel to aluminium at the same
-- quantity -- not adding a second cost, replacing it.

BEGIN;

ALTER TABLE unit_dictionary ADD COLUMN IF NOT EXISTS production_cost_aluminium INTEGER DEFAULT 0;

-- Fighters
UPDATE unit_dictionary
SET production_cost_steel     = 0,
    production_cost_aluminium = 20000
WHERE name = 'fighters';

-- Bombers
UPDATE unit_dictionary
SET production_cost_steel     = 0,
    production_cost_aluminium = 25000
WHERE name = 'bombers';

-- Apaches
UPDATE unit_dictionary
SET production_cost_steel     = 0,
    production_cost_aluminium = 15000
WHERE name = 'apaches';

-- ICBMs
UPDATE unit_dictionary
SET production_cost_steel     = 0,
    production_cost_aluminium = 80000
WHERE name = 'icbms';

-- Nukes
UPDATE unit_dictionary
SET production_cost_steel     = 0,
    production_cost_aluminium = 120000
WHERE name = 'nukes';

COMMIT;
