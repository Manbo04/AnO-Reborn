-- War supplies were replaced by action points, so Organized Supply Lines and
-- Large Storehouses do nothing. Retire them. Looting Teams (a working tech:
-- 30% war plunder) required Organized Supply Lines, so free it up.
UPDATE tech_dictionary SET prerequisite_tech_id = NULL WHERE name = 'looting_teams';
UPDATE tech_dictionary SET is_active = FALSE WHERE name IN ('organized_supply_lines', 'large_storehouses');
