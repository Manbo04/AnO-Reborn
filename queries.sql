UPDATE user_economy SET quantity = quantity + 120000 WHERE user_id = 8 AND resource_id = (SELECT resource_id FROM resource_dictionary WHERE name = 'lumber');
UPDATE user_economy SET quantity = quantity + 50000 WHERE user_id = 8 AND resource_id = (SELECT resource_id FROM resource_dictionary WHERE name = 'iron');
UPDATE user_economy SET quantity = quantity + 50000 WHERE user_id = 8 AND resource_id = (SELECT resource_id FROM resource_dictionary WHERE name = 'coal');
UPDATE user_economy SET quantity = quantity + 350000 WHERE user_id = 8 AND resource_id = (SELECT resource_id FROM resource_dictionary WHERE name = 'rations');
UPDATE user_economy SET quantity = quantity + 15000 WHERE user_id = 8 AND resource_id = (SELECT resource_id FROM resource_dictionary WHERE name = 'steel');
UPDATE user_economy SET quantity = quantity + 10000 WHERE user_id = 8 AND resource_id = (SELECT resource_id FROM resource_dictionary WHERE name = 'components');
UPDATE user_economy SET quantity = quantity + 10000 WHERE user_id = 8 AND resource_id = (SELECT resource_id FROM resource_dictionary WHERE name = 'aluminium');
