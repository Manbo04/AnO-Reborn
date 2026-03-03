-- Migration: Seed Unit Dictionary
-- Date: 2026-03-02
-- Purpose: Populate unit_dictionary with standard military unit types for normalized military system

BEGIN;

-- Insert standard unit types
INSERT INTO unit_dictionary (
    name,
    display_name,
    combat_type,
    base_attack,
    base_defense,
    maintenance_cost_resource_id,
    maintenance_cost_amount,
    manpower_required,
    production_cost_rations,
    production_cost_components,
    production_cost_steel,
    production_cost_fuel,
    description
) VALUES
    (
        'soldiers',
        'Soldiers',
        'infantry',
        1.0,
        1.0,
        1,  -- rations
        1,
        1,
        10,
        0,
        0,
        0,
        'Basic infantry unit with balanced attack and defense'
    ),
    (
        'tanks',
        'Tanks',
        'vehicle',
        10.0,
        10.0,
        2,  -- oil
        5,
        3,
        0,
        50,
        100,
        10,
        'Heavy armor vehicle with superior firepower and durability'
    ),
    (
        'fighters',
        'Fighter Jets',
        'naval',
        50.0,
        30.0,
        2,  -- oil
        20,
        5,
        0,
        200,
        50,
        100,
        'Fast jet fighter with high attack capability'
    ),
    (
        'bombers',
        'Bombers',
        'naval',
        80.0,
        20.0,
        2,  -- oil
        25,
        6,
        0,
        250,
        75,
        150,
        'Heavy bomber with devastating area attack'
    ),
    (
        'destroyers',
        'Destroyers',
        'naval',
        40.0,
        35.0,
        2,  -- oil
        30,
        8,
        0,
        300,
        200,
        50,
        'Fast naval vessel for coastal defense and naval combat'
    ),
    (
        'cruisers',
        'Cruisers',
        'naval',
        60.0,
        50.0,
        2,  -- oil
        40,
        10,
        0,
        400,
        300,
        75,
        'Heavy cruiser for major naval operations'
    ),
    (
        'submarines',
        'Submarines',
        'naval',
        35.0,
        40.0,
        2,  -- oil
        35,
        7,
        0,
        350,
        250,
        60,
        'Stealthy submarine for underwater warfare'
    ),
    (
        'artillery',
        'Artillery',
        'vehicle',
        20.0,
        5.0,
        1,  -- rations
        3,
        2,
        20,
        30,
        50,
        5,
        'Long-range cannon with high attack'
    ),
    (
        'apaches',
        'Apache Helicopters',
        'naval',
        55.0,
        25.0,
        2,  -- oil
        15,
        4,
        0,
        150,
        40,
        80,
        'Attack helicopter with strong offensive capabilities'
    ),
    (
        'spies',
        'Spies',
        'espionage',
        0.0,
        0.0,
        NULL,
        0,
        1,
        5,
        10,
        0,
        0,
        'Intelligence operatives for espionage and reconnaissance'
    ),
    (
        'icbms',
        'ICBMs',
        'strategic',
        100.0,
        0.0,
        2,  -- oil
        50,
        15,
        0,
        500,
        200,
        200,
        'Intercontinental ballistic missiles with massive destructive power'
    ),
    (
        'nukes',
        'Nuclear Warheads',
        'strategic',
        200.0,
        0.0,
        NULL,
        0,
        20,
        0,
        1000,
        500,
        300,
        'Ultimate strategic weapon with extreme destructive capability'
    )
ON CONFLICT (name) DO NOTHING;

COMMIT;
