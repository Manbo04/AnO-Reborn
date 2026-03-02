-- Migration: Normalize Infrastructure and Technology Tables
-- Date: 2026-03-02
-- Purpose: Final phase of normalization - convert wide infrastructure and tech tables to dictionary + mapping pattern
--
-- Key Changes:
-- 1. Create BuildingDictionary to define all building types with costs and effects
-- 2. Create UserBuildings as a mapping table (user_id, building_id, quantity)
-- 3. Create TechDictionary with self-referencing prerequisite system
-- 4. Create UserTech as a mapping table (user_id, tech_id, is_unlocked)
-- 5. Enforce strict foreign key constraints with appropriate cascade rules
-- 6. Create indexes for optimal query performance

-- ============================================================================
-- INFRASTRUCTURE NORMALIZATION
-- ============================================================================

-- Create BuildingDictionary table to store all building type definitions
CREATE TABLE IF NOT EXISTS building_dictionary (
    building_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    display_name VARCHAR(100) NOT NULL,
    category VARCHAR(50) NOT NULL,
    base_cost BIGINT NOT NULL CHECK (base_cost > 0),
    effect_type VARCHAR(50) NOT NULL,
    effect_value NUMERIC(10, 2) NOT NULL,
    maintenance_cost BIGINT DEFAULT 0,
    required_tech_id INTEGER,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    CONSTRAINT building_valid_category CHECK (
        category IN ('energy', 'commerce', 'civic', 'military', 'resource_production', 'infrastructure')
    ),
    CONSTRAINT building_valid_effect_type CHECK (
        effect_type IN ('resource_production', 'population_growth', 'happiness', 'military_boost',
                        'research_speed', 'tax_income', 'energy_production', 'unit_capacity')
    )
);

-- Create UserBuildings mapping table to track building quantities per user
CREATE TABLE IF NOT EXISTS user_buildings (
    user_id INTEGER NOT NULL,
    building_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    last_upgraded TIMESTAMP WITH TIME ZONE DEFAULT now(),
    PRIMARY KEY (user_id, building_id),
    CONSTRAINT fk_user_buildings_user FOREIGN KEY (user_id)
        REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_user_buildings_building FOREIGN KEY (building_id)
        REFERENCES building_dictionary(building_id) ON DELETE RESTRICT
);

-- Indexes for optimal query performance on UserBuildings
CREATE INDEX IF NOT EXISTS idx_user_buildings_user_id ON user_buildings(user_id);
CREATE INDEX IF NOT EXISTS idx_user_buildings_building_id ON user_buildings(building_id);

-- ============================================================================
-- TECHNOLOGY/RESEARCH NORMALIZATION
-- ============================================================================

-- Create TechDictionary table with self-referencing prerequisite system
CREATE TABLE IF NOT EXISTS tech_dictionary (
    tech_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    display_name VARCHAR(100) NOT NULL,
    category VARCHAR(50) NOT NULL,
    research_cost BIGINT NOT NULL CHECK (research_cost > 0),
    prerequisite_tech_id INTEGER,
    effect_type VARCHAR(50),
    effect_value NUMERIC(10, 2),
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    CONSTRAINT fk_tech_prerequisite FOREIGN KEY (prerequisite_tech_id)
        REFERENCES tech_dictionary(tech_id) ON DELETE SET NULL,
    CONSTRAINT tech_valid_category CHECK (
        category IN ('agriculture', 'industry', 'military', 'science', 'infrastructure', 'diplomacy')
    )
);

-- Create UserTech mapping table to track research progress per user
CREATE TABLE IF NOT EXISTS user_tech (
    user_id INTEGER NOT NULL,
    tech_id INTEGER NOT NULL,
    is_unlocked BOOLEAN NOT NULL DEFAULT FALSE,
    research_progress NUMERIC(5, 2) DEFAULT 0 CHECK (research_progress >= 0 AND research_progress <= 100),
    unlocked_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (user_id, tech_id),
    CONSTRAINT fk_user_tech_user FOREIGN KEY (user_id)
        REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_user_tech_tech FOREIGN KEY (tech_id)
        REFERENCES tech_dictionary(tech_id) ON DELETE RESTRICT
);

-- Indexes for optimal query performance on UserTech
CREATE INDEX IF NOT EXISTS idx_user_tech_user_id ON user_tech(user_id);
CREATE INDEX IF NOT EXISTS idx_user_tech_tech_id ON user_tech(tech_id);
CREATE INDEX IF NOT EXISTS idx_user_tech_unlocked ON user_tech(user_id, is_unlocked);

-- Index on prerequisite for efficient tech tree traversal
CREATE INDEX IF NOT EXISTS idx_tech_prerequisite ON tech_dictionary(prerequisite_tech_id);

-- ============================================================================
-- SEED DATA: Building Dictionary
-- ============================================================================

-- Insert base building types across all categories
INSERT INTO building_dictionary (
    name, display_name, category, base_cost, effect_type, effect_value,
    maintenance_cost, description
)
VALUES
    -- Resource Production
    ('farms', 'Farms', 'resource_production', 5000, 'resource_production', 100.0, 50,
     'Agricultural facilities producing rations for population'),
    ('pumpjacks', 'Oil Pumpjacks', 'resource_production', 15000, 'resource_production', 50.0, 150,
     'Extract crude oil from underground reserves'),
    ('coal_mines', 'Coal Mines', 'resource_production', 8000, 'resource_production', 75.0, 100,
     'Extract coal for energy and industrial use'),
    ('steel_mills', 'Steel Mills', 'resource_production', 20000, 'resource_production', 80.0, 200,
     'Process iron ore into steel for construction'),

    -- Energy
    ('coal_burners', 'Coal Power Plants', 'energy', 25000, 'energy_production', 500.0, 300,
     'Generate electricity by burning coal'),
    ('oil_burners', 'Oil Power Plants', 'energy', 30000, 'energy_production', 600.0, 400,
     'Generate electricity by burning oil'),
    ('nuclear_reactors', 'Nuclear Reactors', 'energy', 100000, 'energy_production', 2000.0, 1000,
     'Advanced nuclear power generation'),

    -- Civic
    ('hospitals', 'Hospitals', 'civic', 15000, 'population_growth', 5.0, 200,
     'Medical facilities improving population health and growth'),
    ('universities', 'Universities', 'civic', 25000, 'research_speed', 10.0, 300,
     'Higher education institutions accelerating research'),
    ('libraries', 'Libraries', 'civic', 10000, 'happiness', 3.0, 100,
     'Cultural centers improving citizen happiness'),

    -- Commerce
    ('general_stores', 'General Stores', 'commerce', 8000, 'tax_income', 500.0, 80,
     'Retail establishments generating tax revenue'),
    ('malls', 'Shopping Malls', 'commerce', 35000, 'tax_income', 2000.0, 350,
     'Large commercial centers with high tax yield'),
    ('banks', 'Banks', 'commerce', 50000, 'tax_income', 3000.0, 500,
     'Financial institutions generating significant revenue'),

    -- Military
    ('army_bases', 'Army Bases', 'military', 40000, 'unit_capacity', 1000.0, 400,
     'Military installations increasing ground unit capacity'),
    ('aerodromes', 'Aerodromes', 'military', 60000, 'unit_capacity', 500.0, 600,
     'Air force bases increasing aircraft capacity'),
    ('harbours', 'Harbours', 'military', 55000, 'unit_capacity', 300.0, 550,
     'Naval ports increasing fleet capacity')
ON CONFLICT (name) DO NOTHING;

-- ============================================================================
-- SEED DATA: Tech Dictionary
-- ============================================================================

-- Insert foundational tech tree with prerequisites
INSERT INTO tech_dictionary (name, display_name, category, research_cost, prerequisite_tech_id, effect_type, effect_value, description)
VALUES
    -- Tier 1: Foundation techs (no prerequisites)
    ('basic_agriculture', 'Basic Agriculture', 'agriculture', 5000, NULL, 'resource_production', 10.0,
     'Fundamental farming techniques increasing food production'),
    ('mining_techniques', 'Mining Techniques', 'industry', 6000, NULL, 'resource_production', 10.0,
     'Basic resource extraction methods'),
    ('military_doctrine', 'Military Doctrine', 'military', 8000, NULL, 'military_boost', 5.0,
     'Organized military training and tactics')
ON CONFLICT (name) DO NOTHING;

-- Tier 2: Requires Tier 1
INSERT INTO tech_dictionary (name, display_name, category, research_cost, prerequisite_tech_id, effect_type, effect_value, description)
SELECT
    'industrialization', 'Industrialization', 'industry', 15000,
    (SELECT tech_id FROM tech_dictionary WHERE name = 'mining_techniques'),
    'resource_production', 20.0,
    'Advanced manufacturing and mass production techniques'
WHERE NOT EXISTS (SELECT 1 FROM tech_dictionary WHERE name = 'industrialization');

INSERT INTO tech_dictionary (name, display_name, category, research_cost, prerequisite_tech_id, effect_type, effect_value, description)
SELECT
    'advanced_farming', 'Advanced Farming', 'agriculture', 12000,
    (SELECT tech_id FROM tech_dictionary WHERE name = 'basic_agriculture'),
    'resource_production', 15.0,
    'Improved irrigation and crop rotation methods'
WHERE NOT EXISTS (SELECT 1 FROM tech_dictionary WHERE name = 'advanced_farming');

-- Tier 3: Requires Tier 2
INSERT INTO tech_dictionary (name, display_name, category, research_cost, prerequisite_tech_id, effect_type, effect_value, description)
SELECT
    'scientific_method', 'Scientific Method', 'science', 25000,
    (SELECT tech_id FROM tech_dictionary WHERE name = 'industrialization'),
    'research_speed', 25.0,
    'Systematic approach to research and experimentation'
WHERE NOT EXISTS (SELECT 1 FROM tech_dictionary WHERE name = 'scientific_method');

INSERT INTO tech_dictionary (name, display_name, category, research_cost, prerequisite_tech_id, effect_type, effect_value, description)
SELECT
    'steel_production', 'Steel Production', 'industry', 20000,
    (SELECT tech_id FROM tech_dictionary WHERE name = 'industrialization'),
    'resource_production', 30.0,
    'Bessemer process and advanced metallurgy'
WHERE NOT EXISTS (SELECT 1 FROM tech_dictionary WHERE name = 'steel_production');

-- Tier 4: Advanced techs requiring multiple prerequisite chains
INSERT INTO tech_dictionary (name, display_name, category, research_cost, prerequisite_tech_id, effect_type, effect_value, description)
SELECT
    'nuclear_physics', 'Nuclear Physics', 'science', 50000,
    (SELECT tech_id FROM tech_dictionary WHERE name = 'scientific_method'),
    'military_boost', 50.0,
    'Atomic theory and nuclear energy harnessing'
WHERE NOT EXISTS (SELECT 1 FROM tech_dictionary WHERE name = 'nuclear_physics');

-- Add foreign key for buildings requiring specific tech
ALTER TABLE building_dictionary
ADD CONSTRAINT fk_building_required_tech
FOREIGN KEY (required_tech_id) REFERENCES tech_dictionary(tech_id) ON DELETE SET NULL;

-- ============================================================================
-- MIGRATION NOTES FOR MANUAL EXECUTION
-- ============================================================================
--
-- IMPORTANT: This migration creates NEW normalized tables alongside existing ones:
-- - building_dictionary (replaces proInfra column-per-building pattern)
-- - user_buildings (new mapping table for building ownership)
-- - tech_dictionary (replaces upgrades column-per-tech pattern)
-- - user_tech (new mapping table for tech research progress)
--
-- DATA MIGRATION STEPS (to be executed manually in DBeaver):
--
-- 1. Building Migration:
--    a. For each building column in proInfra, lookup building_id from building_dictionary
--    b. For each user in proInfra, INSERT into user_buildings (user_id, building_id, quantity)
--       where quantity = proInfra.<building_column_name>
--    c. Verify foreign key constraints are satisfied
--    d. When ready: DROP TABLE proInfra;
--
-- 2. Tech Migration:
--    a. For each upgrade column in upgrades table, lookup tech_id from tech_dictionary
--    b. For each user in upgrades, INSERT into user_tech (user_id, tech_id, is_unlocked)
--       where is_unlocked = (upgrades.<tech_column_name> > 0)
--    c. Verify foreign key constraints are satisfied
--    d. When ready: DROP TABLE upgrades;
--
-- 3. Tech Tree Validation:
--    Query to verify prerequisite chain integrity:
--    SELECT t1.name, t2.name as prerequisite
--    FROM tech_dictionary t1
--    LEFT JOIN tech_dictionary t2 ON t1.prerequisite_tech_id = t2.tech_id
--    ORDER BY t1.tech_id;
--
-- FOREIGN KEY ENFORCEMENT:
-- All new tables enforce referential integrity at the database level.
-- Self-referencing FK in tech_dictionary creates directed tech tree graph.
--
-- ============================================================================
-- INTEGRITY NOTES
-- ============================================================================
--
-- Foreign Key Constraints:
-- - user_buildings.user_id → users.id with ON DELETE CASCADE
--   (Buildings removed when user deleted)
-- - user_buildings.building_id → building_dictionary.building_id with ON DELETE RESTRICT
--   (Cannot delete building definitions while users own them)
--
-- - user_tech.user_id → users.id with ON DELETE CASCADE
--   (Research progress removed when user deleted)
-- - user_tech.tech_id → tech_dictionary.tech_id with ON DELETE RESTRICT
--   (Cannot delete tech definitions while users have researched them)
--
-- - tech_dictionary.prerequisite_tech_id → tech_dictionary.tech_id with ON DELETE SET NULL
--   (Self-referencing for tech tree dependencies)
-- - building_dictionary.required_tech_id → tech_dictionary.tech_id with ON DELETE SET NULL
--   (Buildings can require specific techs to unlock)
--
-- Indexes:
-- - Building: Fast lookups by user and building type
-- - Tech: Fast queries for user research progress and tech tree traversal
-- - Prerequisite: Efficient lookup of dependent techs
--
-- CHECK Constraints:
-- - building_dictionary.base_cost > 0: No free buildings
-- - user_buildings.quantity >= 0: No negative building counts
-- - tech_dictionary.research_cost > 0: No free research
-- - user_tech.research_progress: Must be between 0 and 100 percent
-- - building_dictionary.category: Valid building classification
-- - building_dictionary.effect_type: Valid effect classification
-- - tech_dictionary.category: Valid tech classification
--
-- Tech Tree Design:
-- The self-referencing prerequisite_tech_id enables complex tech dependency chains.
-- Example: Nuclear Physics requires Scientific Method, which requires Industrialization.
-- Application logic should validate prerequisites before allowing research to begin.
