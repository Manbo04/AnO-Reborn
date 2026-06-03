-- ============================================================================
-- Tech Tree Realism and Prerequisite Rebalance
-- ============================================================================

-- Nuclear Progression
UPDATE tech_dictionary 
SET prerequisite_tech_id = (SELECT tech_id FROM tech_dictionary WHERE name = 'better_engineering')
WHERE name = 'nuclear_testing_facility';

UPDATE tech_dictionary 
SET prerequisite_tech_id = (SELECT tech_id FROM tech_dictionary WHERE name = 'nuclear_testing_facility')
WHERE name = 'ballistic_missile_silo';

UPDATE tech_dictionary 
SET prerequisite_tech_id = (SELECT tech_id FROM tech_dictionary WHERE name = 'ballistic_missile_silo')
WHERE name = 'icbm_silo';

-- Propaganda Progression
UPDATE tech_dictionary 
SET prerequisite_tech_id = (SELECT tech_id FROM tech_dictionary WHERE name = 'government_regulation')
WHERE name = 'widespread_propaganda';

-- Looting Progression
UPDATE tech_dictionary 
SET prerequisite_tech_id = (SELECT tech_id FROM tech_dictionary WHERE name = 'organized_supply_lines')
WHERE name = 'looting_teams';
