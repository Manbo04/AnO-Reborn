-- Migration: 0066 - Kamikaze drones, cruise missiles, aircraft carriers
-- Date: 2026-09-05
-- Discord (The_kaiser, #suggestions "add kamikaze drones", 2026-08-25): a cheap
-- expendable drone unit produced by a new "drone site" building into a capped
-- stockpile, activated/launched by the player. AnO's triage bot logged it
-- 2026-09-01 as needing Dede's balance call before wiring in -- this is that.
-- Dede additionally asked to generalize the produce-into-a-stockpile pattern
-- ("we could add that to most military things") and grow the roster a bit.
--
-- This adds:
--   - kamikaze_drones + drone_sites (new "unit_production" building type --
--     no building has ever produced units before, only resources)
--   - cruise_missiles + missile_batteries (same pattern, fills the real gap
--     between bombers at 22,000 gold and icbms at 16,000,000 gold)
--   - aircraft_carriers (traditional roster unit, bought directly like
--     existing ships -- fills the missing naval capital-ship tier)
--
-- production_cost_* on kamikaze_drones/cruise_missiles is repurposed: instead
-- of being debited when the player buys the unit (there is no direct buy for
-- these), it's debited by the hourly tick each time the drone site/missile
-- battery manufactures one into the stockpile. aircraft_carriers uses
-- production_cost_* the normal way (debited at purchase, via MILDICT for the
-- gold price, same flow as every other ship).
--
-- user_unit_stockpile is a new table, deliberately separate from
-- user_military: user_military.quantity means "combat-ready, owned"; this
-- table means "manufactured but not yet activated". The activation route
-- (app_core/military/services.py::process_activate_units) moves quantity
-- from here into user_military for a gold-only price -- resources were
-- already spent when the tick produced the unit.

BEGIN;

-- Allow buildings whose effect is "produces a unit into a stockpile", not
-- just a resource.
ALTER TABLE building_dictionary DROP CONSTRAINT IF EXISTS building_valid_effect_type;
ALTER TABLE building_dictionary ADD CONSTRAINT building_valid_effect_type CHECK (
    effect_type IN ('resource_production', 'population_growth', 'happiness', 'military_boost',
                    'research_speed', 'tax_income', 'energy_production', 'unit_capacity',
                    'unit_production')
);

CREATE TABLE IF NOT EXISTS user_unit_stockpile (
    user_id INTEGER NOT NULL,
    unit_id INTEGER NOT NULL,
    quantity BIGINT NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    PRIMARY KEY (user_id, unit_id),
    CONSTRAINT fk_user_unit_stockpile_user FOREIGN KEY (user_id)
        REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_user_unit_stockpile_unit FOREIGN KEY (unit_id)
        REFERENCES unit_dictionary(unit_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_user_unit_stockpile_user_id ON user_unit_stockpile(user_id);

INSERT INTO building_dictionary (name, display_name, category, base_cost, effect_type, effect_value, maintenance_cost, description)
VALUES
    (
        'drone_sites', 'Drone Site', 'military', 15000000, 'unit_production', 10, 5000,
        'Manufactures kamikaze drones over time into a stockpile (10/site) you can activate into your military.'
    ),
    (
        'missile_batteries', 'Missile Battery', 'military', 120000000, 'unit_production', 5, 40000,
        'Manufactures cruise missiles over time into a stockpile (5/battery) you can activate into your military.'
    )
ON CONFLICT (name) DO NOTHING;

INSERT INTO unit_dictionary (
    name, display_name, combat_type, base_attack, base_defense,
    maintenance_cost_resource_id, maintenance_cost_amount, manpower_required,
    production_cost_rations, production_cost_components, production_cost_steel,
    production_cost_fuel, production_cost_aluminium, production_cost_uranium,
    description
)
SELECT
    'kamikaze_drones', 'Kamikaze Drones', 'strategic', 1.5, 0.0,
    (SELECT resource_id FROM resource_dictionary WHERE name = 'gasoline'), 5, 0,
    0, 400, 0, 0, 800, 0,
    'Cheap expendable loitering munition. Weak alone -- meant to be launched in swarms at enemy buildings.'
UNION ALL
SELECT
    'cruise_missiles', 'Cruise Missiles', 'strategic', 4.0, 0.0,
    (SELECT resource_id FROM resource_dictionary WHERE name = 'gasoline'), 20, 0,
    0, 8000, 5000, 0, 12000, 0,
    'Precision-guided missile. Pricier and slower to produce than drones, but a guaranteed hit.'
UNION ALL
SELECT
    'aircraft_carriers', 'Aircraft Carriers', 'naval', 3.0, 3.5,
    (SELECT resource_id FROM resource_dictionary WHERE name = 'gasoline'), 60, 12,
    0, 60000, 400000, 20000, 200000, 0,
    'Naval capital ship. Extends the reach of your air wing -- each carrier raises your fighter/bomber capacity.'
ON CONFLICT (name) DO NOTHING;

COMMIT;
