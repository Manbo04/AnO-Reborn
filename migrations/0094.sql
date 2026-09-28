-- Register the five new buildings (railways, metros, firewatch_towers, levees,
-- seismic_reinforcements) in building_dictionary.  The table has no unit_type
-- column; the required NOT NULL columns are:
--   name, display_name, category, base_cost, effect_type, effect_value,
--   maintenance_cost, description
-- effect_type must be one of the values in the building_valid_effect_type CHECK
-- constraint added by migrations/0066*.sql.

BEGIN;

INSERT INTO building_dictionary
    (name, display_name, category, base_cost, effect_type, effect_value, maintenance_cost, description)
VALUES
    ('railways',              'Railways',                 'civic',    62500000,  'resource_production', 8.00,   67500,  'Regional rail network boosting productivity.'),
    ('metros',                'Metros',                   'civic',   150000000,  'resource_production', 12.00, 150000,  'Urban metro system significantly boosting productivity.'),
    ('firewatch_towers',      'Firewatch Towers',         'civic',      15000,   'resource_production',  0.00,   1000,  'Fire lookout towers reducing wildfire disaster risk.'),
    ('levees',                'Levees',                   'civic',      75000,   'resource_production',  0.00,   3000,  'Flood barriers reducing flood and monsoon disaster risk.'),
    ('seismic_reinforcements','Seismic Reinforcements',   'civic',     150000,   'resource_production',  0.00,   5000,  'Earthquake-resistant infrastructure reducing rockslide disaster risk.')
ON CONFLICT (name) DO NOTHING;

COMMIT;
