BEGIN;

-- Migration 0084: Air defense SAM batteries
-- SAM batteries (bought like other military units, with upkeep) intercept drones and missiles.

INSERT INTO unit_dictionary (
    name, display_name, combat_type, base_attack, base_defense,
    maintenance_cost_resource_id, maintenance_cost_amount, manpower_required,
    production_cost_rations, production_cost_components, production_cost_steel,
    production_cost_fuel, production_cost_aluminium, production_cost_uranium,
    description
)
SELECT
    'sam_batteries', 'SAM Batteries', 'strategic', 0.0, 5.0,
    (SELECT resource_id FROM resource_dictionary WHERE name = 'gasoline'), 15, 3,
    0, 4000, 15000, 0, 5000, 0,
    'Surface-to-Air Missile battery. Automatically intercepts incoming Kamikaze Drones and Cruise Missiles.'
ON CONFLICT (name) DO NOTHING;

COMMIT;
