-- Migration: 0014 - Economy 2.0 unit upkeep and build cost rebalance
-- Date: 2026-03-05
-- Purpose:
--   1. Reset maintenance_cost_amount to weight-scaled values so a single
--      Oil Refinery (75,000 kg gasoline/tick) supports a realistic army.
--   2. Fix apaches maintenance resource from oil → gasoline (was inconsistent).
--   3. Scale production costs to the new kg weight system.
--
-- NEW UPKEEP (kg/tick):
--   soldiers   50 rations
--   tanks      250 gasoline   (1 refinery = 300 tanks)
--   artillery  150 gasoline   (1 refinery = 500 artillery)
--   fighters   500 gasoline   (1 refinery = 150 fighters)
--   bombers    500 gasoline
--   apaches    500 gasoline
--   destroyers 500 gasoline
--   cruisers   750 gasoline
--   submarines 400 gasoline
--   icbms      1000 gasoline
--   nukes      NULL (no maintenance)
--   spies      50 components
--
-- NEW BUILD COSTS (kg, weight-based):
--   soldiers:  500 rations
--   tanks:     50,000 steel + 5,000 components + 2,000 fuel
--   artillery: 30,000 steel + 3,000 components + 1,000 fuel
--   fighters:  20,000 steel + 10,000 components + 5,000 fuel
--   bombers:   25,000 steel + 15,000 components + 8,000 fuel
--   apaches:   15,000 steel + 8,000 components  + 3,000 fuel

BEGIN;

-- ── Upkeep amounts ────────────────────────────────────────────────────────────
UPDATE unit_dictionary
SET maintenance_cost_amount = 50
WHERE name = 'soldiers';

UPDATE unit_dictionary
SET maintenance_cost_amount = 250
WHERE name = 'tanks';

UPDATE unit_dictionary
SET maintenance_cost_amount = 150,
    -- artillery was seeded with rations in some environments; force gasoline
    maintenance_cost_resource_id = (
        SELECT resource_id FROM resource_dictionary WHERE name = 'gasoline'
    )
WHERE name = 'artillery';

UPDATE unit_dictionary
SET maintenance_cost_amount = 500,
    -- fix apaches: was 'oil', should be 'gasoline'
    maintenance_cost_resource_id = (
        SELECT resource_id FROM resource_dictionary WHERE name = 'gasoline'
    )
WHERE name = 'apaches';

UPDATE unit_dictionary
SET maintenance_cost_amount = 500
WHERE name IN ('fighters', 'bombers');

UPDATE unit_dictionary
SET maintenance_cost_amount = 500
WHERE name = 'destroyers';

UPDATE unit_dictionary
SET maintenance_cost_amount = 750
WHERE name = 'cruisers';

UPDATE unit_dictionary
SET maintenance_cost_amount = 400
WHERE name = 'submarines';

UPDATE unit_dictionary
SET maintenance_cost_amount = 1000
WHERE name = 'icbms';

UPDATE unit_dictionary
SET maintenance_cost_amount = 50
WHERE name = 'spies';

-- Nukes have no ongoing maintenance
UPDATE unit_dictionary
SET maintenance_cost_resource_id = NULL,
    maintenance_cost_amount = 0
WHERE name = 'nukes';

-- ── Build costs (production_cost_*) ─────────────────────────────────────────
UPDATE unit_dictionary
SET production_cost_rations    = 500,
    production_cost_steel      = 0,
    production_cost_components = 0,
    production_cost_fuel       = 0
WHERE name = 'soldiers';

UPDATE unit_dictionary
SET production_cost_rations    = 0,
    production_cost_steel      = 50000,
    production_cost_components = 5000,
    production_cost_fuel       = 2000
WHERE name = 'tanks';

UPDATE unit_dictionary
SET production_cost_rations    = 0,
    production_cost_steel      = 30000,
    production_cost_components = 3000,
    production_cost_fuel       = 1000
WHERE name = 'artillery';

UPDATE unit_dictionary
SET production_cost_rations    = 0,
    production_cost_steel      = 20000,
    production_cost_components = 10000,
    production_cost_fuel       = 5000
WHERE name = 'fighters';

UPDATE unit_dictionary
SET production_cost_rations    = 0,
    production_cost_steel      = 25000,
    production_cost_components = 15000,
    production_cost_fuel       = 8000
WHERE name = 'bombers';

UPDATE unit_dictionary
SET production_cost_rations    = 0,
    production_cost_steel      = 15000,
    production_cost_components = 8000,
    production_cost_fuel       = 3000
WHERE name = 'apaches';

COMMIT;
