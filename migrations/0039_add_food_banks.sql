SELECT setval(pg_get_serial_sequence('building_dictionary', 'building_id'), coalesce(max(building_id), 0) + 1, false) FROM building_dictionary;

INSERT INTO building_dictionary (
    name, display_name, description, category, base_cost, effect_type, effect_value, maintenance_cost
)
VALUES (
    'food_banks', 'Food Banks', 'Cheap distribution building to distribute rations to the populace.', 'infrastructure', 250000, 'population_growth', 250000, 2500
)
ON CONFLICT (name) DO NOTHING;
