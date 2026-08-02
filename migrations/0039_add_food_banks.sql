INSERT INTO building_dictionary (name, display_name, description, category, required_level)
VALUES ('food_banks', 'Food Banks', 'Cheap distribution building to distribute rations to the populace.', 'retail', 1)
ON CONFLICT (name) DO NOTHING;
