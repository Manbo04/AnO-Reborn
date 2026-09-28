INSERT INTO building_dictionary (name, unit_type) VALUES 
('railways', 'civilian'),
('metros', 'civilian'),
('firewatch_towers', 'civilian'),
('levees', 'civilian'),
('seismic_reinforcements', 'civilian')
ON CONFLICT (name) DO NOTHING;
