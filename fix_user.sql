INSERT INTO stats (id, location, gold) VALUES (8, 1, 0) ON CONFLICT DO NOTHING;
INSERT INTO policies (user_id) VALUES (8) ON CONFLICT DO NOTHING;

INSERT INTO user_economy (user_id, resource_id, quantity) 
SELECT 8, resource_id, 0 FROM resource_dictionary ON CONFLICT DO NOTHING;

INSERT INTO user_military (user_id, unit_id, quantity) 
SELECT 8, unit_id, 0 FROM unit_dictionary ON CONFLICT DO NOTHING;

INSERT INTO users_statistics (user_id) VALUES (8) ON CONFLICT DO NOTHING;
