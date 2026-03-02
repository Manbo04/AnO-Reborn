-- Migration: Normalize Economy and Military Tables
-- Date: 2026-03-02
-- Purpose: Shift from wide tables to normalized architecture with Dictionary and Mapping tables
--
-- Key Changes:
-- 1. Create ResourceDictionary to define all resource types (food, oil, coal, etc.)
-- 2. Create UserEconomy as a mapping table (user_id, resource_id, quantity)
-- 3. Create UnitDictionary to define all unit types with combat stats
-- 4. Create UserMilitary as a mapping table (user_id, unit_id, quantity)
-- 5. Enforce strict foreign key constraints with appropriate cascade rules
-- 6. Create indexes for optimal query performance

-- ============================================================================
-- RESOURCE NORMALIZATION
-- ============================================================================

-- Create ResourceDictionary table to store all resource types and their properties
CREATE TABLE IF NOT EXISTS resource_dictionary (
    resource_id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    display_name VARCHAR(100) NOT NULL,
    description TEXT,
    is_production BOOLEAN DEFAULT FALSE,  -- True if resource is produced (not raw)
    is_raw BOOLEAN DEFAULT FALSE,         -- True if raw material
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    CONSTRAINT resource_unique_display_name UNIQUE (display_name)
);

-- Create UserEconomy mapping table to track quantities per user
CREATE TABLE IF NOT EXISTS user_economy (
    user_id INTEGER NOT NULL,
    resource_id INTEGER NOT NULL,
    quantity BIGINT NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    PRIMARY KEY (user_id, resource_id),
    CONSTRAINT fk_user_economy_user FOREIGN KEY (user_id)
        REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_user_economy_resource FOREIGN KEY (resource_id)
        REFERENCES resource_dictionary(resource_id) ON DELETE RESTRICT
);

-- Indexes for optimal query performance on UserEconomy
CREATE INDEX IF NOT EXISTS idx_user_economy_user_id ON user_economy(user_id);
CREATE INDEX IF NOT EXISTS idx_user_economy_resource_id ON user_economy(resource_id);

-- ============================================================================
-- MILITARY NORMALIZATION
-- ============================================================================

-- Create UnitDictionary table to store unit definitions with combat attributes
CREATE TABLE IF NOT EXISTS unit_dictionary (
    unit_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    display_name VARCHAR(100) NOT NULL,
    combat_type VARCHAR(50) NOT NULL,  -- 'infantry', 'vehicle', 'naval', 'espionage', 'strategic'
    base_attack NUMERIC(10, 2) NOT NULL DEFAULT 0,
    base_defense NUMERIC(10, 2) NOT NULL DEFAULT 0,
    maintenance_cost_resource_id INTEGER,  -- Reference to primary maintenance resource (e.g., fuel, rations)
    maintenance_cost_amount BIGINT DEFAULT 0,
    manpower_required BIGINT DEFAULT 0,  -- Population/manpower to build/maintain
    production_cost_rations BIGINT DEFAULT 0,
    production_cost_components BIGINT DEFAULT 0,
    production_cost_steel BIGINT DEFAULT 0,
    production_cost_fuel BIGINT DEFAULT 0,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    CONSTRAINT fk_unit_maintenance_resource FOREIGN KEY (maintenance_cost_resource_id)
        REFERENCES resource_dictionary(resource_id) ON DELETE SET NULL,
    CONSTRAINT unit_valid_combat_type CHECK (
        combat_type IN ('infantry', 'vehicle', 'naval', 'espionage', 'strategic')
    )
);

-- Create UserMilitary mapping table to track unit quantities per user
CREATE TABLE IF NOT EXISTS user_military (
    user_id INTEGER NOT NULL,
    unit_id INTEGER NOT NULL,
    quantity BIGINT NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    PRIMARY KEY (user_id, unit_id),
    CONSTRAINT fk_user_military_user FOREIGN KEY (user_id)
        REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_user_military_unit FOREIGN KEY (unit_id)
        REFERENCES unit_dictionary(unit_id) ON DELETE RESTRICT
);

-- Indexes for optimal query performance on UserMilitary
CREATE INDEX IF NOT EXISTS idx_user_military_user_id ON user_military(user_id);
CREATE INDEX IF NOT EXISTS idx_user_military_unit_id ON user_military(unit_id);
CREATE INDEX IF NOT EXISTS idx_user_military_combat_type ON unit_dictionary(combat_type);

-- ============================================================================
-- SEED DATA: Resource Dictionary
-- ============================================================================

-- Insert base resources (raw materials and production)
INSERT INTO resource_dictionary (name, display_name, description, is_production, is_raw)
VALUES
    ('rations', 'Rations', 'Food resources for population sustenance', false, true),
    ('oil', 'Oil', 'Raw oil for fuel and production', false, true),
    ('coal', 'Coal', 'Raw coal for energy', false, true),
    ('uranium', 'Uranium', 'Raw uranium for advanced weapons', false, true),
    ('bauxite', 'Bauxite', 'Raw ore for aluminium production', false, true),
    ('iron', 'Iron', 'Raw iron ore', false, true),
    ('lead', 'Lead', 'Raw lead for ammunition', false, true),
    ('copper', 'Copper', 'Raw copper for components', false, true),
    ('lumber', 'Lumber', 'Wood for construction', false, true),
    ('components', 'Components', 'Manufactured military components', true, false),
    ('steel', 'Steel', 'Refined steel for construction and military', true, false),
    ('consumer_goods', 'Consumer Goods', 'Goods for civilian population', true, false),
    ('aluminium', 'Aluminium', 'Refined aluminium for aircraft', true, false),
    ('gasoline', 'Gasoline', 'Refined fuel for vehicles and aircraft', true, false),
    ('ammunition', 'Ammunition', 'Manufactured ammunition for military', true, false)
ON CONFLICT (name) DO NOTHING;

-- ============================================================================
-- SEED DATA: Unit Dictionary
-- ============================================================================

-- Insert base military units with combat attributes
INSERT INTO unit_dictionary (
    name, display_name, combat_type, base_attack, base_defense,
    maintenance_cost_resource_id, maintenance_cost_amount,
    production_cost_rations, production_cost_components, production_cost_steel, production_cost_fuel,
    description
)
SELECT
    'soldiers', 'Soldiers', 'infantry', 1.0, 1.5,
    (SELECT resource_id FROM resource_dictionary WHERE name = 'rations'), 1,
    100, 0, 0, 0,
    'Basic infantry unit for ground combat'
UNION ALL
SELECT
    'tanks', 'Tanks', 'vehicle', 3.0, 2.5,
    (SELECT resource_id FROM resource_dictionary WHERE name = 'gasoline'), 10,
    200, 150, 200, 50,
    'Armored ground vehicle for heavy combat'
UNION ALL
SELECT
    'artillery', 'Artillery', 'vehicle', 2.5, 1.0,
    (SELECT resource_id FROM resource_dictionary WHERE name = 'gasoline'), 8,
    300, 100, 150, 30,
    'Long-range ground weapon system'
UNION ALL
SELECT
    'fighters', 'Fighters', 'naval', 2.0, 1.5,
    (SELECT resource_id FROM resource_dictionary WHERE name = 'gasoline'), 15,
    250, 200, 100, 100,
    'Jet fighter aircraft'
UNION ALL
SELECT
    'bombers', 'Bombers', 'naval', 3.5, 1.0,
    (SELECT resource_id FROM resource_dictionary WHERE name = 'gasoline'), 20,
    400, 300, 150, 150,
    'Heavy bomber aircraft'
UNION ALL
SELECT
    'destroyers', 'Destroyers', 'naval', 2.0, 2.0,
    (SELECT resource_id FROM resource_dictionary WHERE name = 'gasoline'), 25,
    500, 400, 300, 100,
    'Fast naval warship'
UNION ALL
SELECT
    'cruisers', 'Cruisers', 'naval', 2.5, 2.5,
    (SELECT resource_id FROM resource_dictionary WHERE name = 'gasoline'), 30,
    600, 500, 400, 150,
    'Medium naval warship'
UNION ALL
SELECT
    'submarines', 'Submarines', 'naval', 1.5, 3.0,
    (SELECT resource_id FROM resource_dictionary WHERE name = 'gasoline'), 20,
    700, 600, 500, 200,
    'Stealth underwater naval unit'
UNION ALL
SELECT
    'spies', 'Spies', 'espionage', 0.5, 0.5,
    (SELECT resource_id FROM resource_dictionary WHERE name = 'components'), 5,
    100, 200, 0, 0,
    'Intelligence and espionage unit'
UNION ALL
SELECT
    'icbms', 'ICBMs', 'strategic', 5.0, 0.0,
    (SELECT resource_id FROM resource_dictionary WHERE name = 'gasoline'), 50,
    1000, 800, 600, 300,
    'Intercontinental ballistic missile'
UNION ALL
SELECT
    'nukes', 'Nuclear Warheads', 'strategic', 10.0, 0.0,
    (SELECT resource_id FROM resource_dictionary WHERE name = 'uranium'), 100,
    2000, 1500, 1000, 500,
    'Nuclear deterrent weapon'
ON CONFLICT (name) DO NOTHING;

-- ============================================================================
-- INTEGRITY NOTES
-- ============================================================================
--
-- Foreign Key Constraints:
-- - user_economy.user_id → users.id with ON DELETE CASCADE
--   (Resources are automatically cleaned when user deleted)
-- - user_economy.resource_id → resource_dictionary.resource_id with ON DELETE RESTRICT
--   (Cannot delete resource definitions while mappings exist; ensures data consistency)
--
-- - user_military.user_id → users.id with ON DELETE CASCADE
--   (Units are automatically cleaned when user deleted)
-- - user_military.unit_id → unit_dictionary.unit_id with ON DELETE RESTRICT
--   (Cannot delete unit definitions while mappings exist; ensures data consistency)
--
-- Indexes:
-- - idx_user_economy_user_id: Speeds up lookups like "get all resources for user X"
-- - idx_user_economy_resource_id: Speeds up lookups like "get all users with resource X"
-- - idx_user_military_user_id: Speeds up lookups like "get all units for user X"
-- - idx_user_military_unit_id: Speeds up lookups like "get all users with unit X"
-- - idx_user_military_combat_type: Speeds up combat phase filtering by unit type
--
-- CHECK Constraints:
-- - user_economy.quantity >= 0: Prevents negative resources
-- - user_military.quantity >= 0: Prevents negative unit counts
-- - unit_dictionary.combat_type IN (...): Ensures valid combat classifications
