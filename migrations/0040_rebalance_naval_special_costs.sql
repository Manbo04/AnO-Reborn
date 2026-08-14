-- Migration: 0040 - Rebalance naval and special unit build costs to weight-scaled values
-- Date: 2026-08-15

BEGIN;

-- Destroyers
UPDATE unit_dictionary
SET production_cost_rations    = 0,
    production_cost_steel      = 120000,
    production_cost_components = 15000,
    production_cost_fuel       = 4000
WHERE name = 'destroyers';

-- Cruisers
UPDATE unit_dictionary
SET production_cost_rations    = 0,
    production_cost_steel      = 200000,
    production_cost_components = 25000,
    production_cost_fuel       = 6000
WHERE name = 'cruisers';

-- Submarines
UPDATE unit_dictionary
SET production_cost_rations    = 0,
    production_cost_steel      = 150000,
    production_cost_components = 20000,
    production_cost_fuel       = 5000
WHERE name = 'submarines';

-- Spies
UPDATE unit_dictionary
SET production_cost_rations    = 100,
    production_cost_steel      = 0,
    production_cost_components = 2000,
    production_cost_fuel       = 0
WHERE name = 'spies';

-- ICBMs
UPDATE unit_dictionary
SET production_cost_rations    = 0,
    production_cost_steel      = 80000,
    production_cost_components = 50000,
    production_cost_fuel       = 15000
WHERE name = 'icbms';

-- Nukes
UPDATE unit_dictionary
SET production_cost_rations    = 0,
    production_cost_steel      = 120000,
    production_cost_components = 100000,
    production_cost_fuel       = 25000
WHERE name = 'nukes';

COMMIT;
