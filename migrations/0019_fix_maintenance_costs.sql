-- Migration: 0019 - Fix military maintenance costs to match actual production rates
-- Date: 2026-03-13
-- Purpose: Maintenance values from 0014 assumed ~75,000 production/building/tick
--   but actual production via generate_province_revenue is only ~11-60/building/hour.
--   global_tick consumes 6x/hr, creating a 6:1 consumption-to-production ratio
--   that zeroed out every player's rations and gasoline within minutes.
--   This migration resets maintenance to sustainable values.

BEGIN;

UPDATE unit_dictionary SET maintenance_cost_amount = 1  WHERE name = 'soldiers';
UPDATE unit_dictionary SET maintenance_cost_amount = 2  WHERE name = 'tanks';
UPDATE unit_dictionary SET maintenance_cost_amount = 1  WHERE name = 'artillery';
UPDATE unit_dictionary SET maintenance_cost_amount = 3  WHERE name = 'fighters';
UPDATE unit_dictionary SET maintenance_cost_amount = 3  WHERE name = 'bombers';
UPDATE unit_dictionary SET maintenance_cost_amount = 3  WHERE name = 'apaches';
UPDATE unit_dictionary SET maintenance_cost_amount = 3  WHERE name = 'destroyers';
UPDATE unit_dictionary SET maintenance_cost_amount = 5  WHERE name = 'cruisers';
UPDATE unit_dictionary SET maintenance_cost_amount = 2  WHERE name = 'submarines';
UPDATE unit_dictionary SET maintenance_cost_amount = 5  WHERE name = 'icbms';
UPDATE unit_dictionary SET maintenance_cost_amount = 1  WHERE name = 'spies';

COMMIT;
