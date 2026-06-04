-- Fix base_cost in building_dictionary for economy rebalance buildings
-- They were accidentally given their MONEY cost instead of their STEEL cost

UPDATE building_dictionary SET base_cost = 120000 WHERE name = 'hydro_dams';
UPDATE building_dictionary SET base_cost = 60000 WHERE name = 'gas_stations';
UPDATE building_dictionary SET base_cost = 110000 WHERE name = 'farmers_markets';
UPDATE building_dictionary SET base_cost = 22000 WHERE name = 'city_parks';
UPDATE building_dictionary SET base_cost = 600000 WHERE name = 'monorails';
UPDATE building_dictionary SET base_cost = 135000 WHERE name = 'admin_buildings';
UPDATE building_dictionary SET base_cost = 1080000 WHERE name = 'silos';
UPDATE building_dictionary SET base_cost = 45000 WHERE name = 'lead_mines';
UPDATE building_dictionary SET base_cost = 45000 WHERE name = 'distribution_centers';
