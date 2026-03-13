-- Migration: 0014 - Economy 2.0 unit upkeep and build cost rebalance
-- Date: 2026-03-05
-- Updated: 2026-03-13 — Corrected maintenance values to match actual
--   production rates from generate_province_revenue (NEW_INFRA).
--   Original values assumed ~75,000 production per building per tick,
--   but actual production is ~11-60 per building per hour with
--   global_tick consuming 6x/hr.  All maintenance reduced accordingly.
--
-- NEW UPKEEP (per global_tick, runs every 10 min):
--   soldiers   1  ration      (1 farm ≈ 10 soldiers at 16 land)
--   tanks      2  gasoline    (1 oil_refinery ≈ 1 tank)
--   artillery  1  gasoline    (1 oil_refinery ≈ 2 artillery)
--   fighters   3  gasoline    (need several refineries per wing)
--   bombers    3  gasoline
--   apaches    3  gasoline
--   destroyers 3  gasoline
--   cruisers   5  gasoline
--   submarines 2  gasoline
--   icbms      5  gasoline
--   nukes      0  (no maintenance)
--   spies      1  components
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
SET maintenance_cost_amount = 1
WHERE name = 'soldiers';

UPDATE unit_dictionary
SET maintenance_cost_amount = 2
WHERE name = 'tanks';

UPDATE unit_dictionary
SET maintenance_cost_amount = 1,
    -- artillery was seeded with rations in some environments; force gasoline
    maintenance_cost_resource_id = (
        SELECT resource_id FROM resource_dictionary WHERE name = 'gasoline'
    )
WHERE name = 'artillery';

UPDATE unit_dictionary
SET maintenance_cost_amount = 3,
    -- fix apaches: was 'oil', should be 'gasoline'
    maintenance_cost_resource_id = (
        SELECT resource_id FROM resource_dictionary WHERE name = 'gasoline'
    )
WHERE name = 'apaches';

UPDATE unit_dictionary
SET maintenance_cost_amount = 3
WHERE name IN ('fighters', 'bombers');

UPDATE unit_dictionary
SET maintenance_cost_amount = 3
WHERE name = 'destroyers';

UPDATE unit_dictionary
SET maintenance_cost_amount = 5
WHERE name = 'cruisers';

UPDATE unit_dictionary
SET maintenance_cost_amount = 2
WHERE name = 'submarines';

UPDATE unit_dictionary
SET maintenance_cost_amount = 5
WHERE name = 'icbms';

UPDATE unit_dictionary
SET maintenance_cost_amount = 1
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
