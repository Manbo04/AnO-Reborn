-- Activation gift for ledger_goods_use: 72 hours of each need (clothing per 200k pop, medicine 2/hospital, fertilizer 1/farm) to every non-bot nation. Realm only.
WITH need AS (
  SELECT u.id AS uid,
    CEIL(COALESCE((SELECT SUM(population) FROM provinces p WHERE p.userid = u.id),0) / 200000.0) * 72 AS clothing,
    COALESCE((SELECT SUM(ub.quantity) FROM user_buildings ub JOIN building_dictionary bd USING(building_id) WHERE ub.user_id = u.id AND bd.name='hospitals'),0) * 2 * 72 AS medicine,
    COALESCE((SELECT SUM(ub.quantity) FROM user_buildings ub JOIN building_dictionary bd USING(building_id) WHERE ub.user_id = u.id AND bd.name='farms'),0) * 72 AS fertilizer
  FROM users u WHERE u.auth_type <> 'bot')
UPDATE user_economy ue SET quantity = ue.quantity + CASE rd.name WHEN 'clothing' THEN n.clothing WHEN 'medicine' THEN n.medicine WHEN 'fertilizer' THEN n.fertilizer END
FROM need n, resource_dictionary rd
WHERE ue.user_id = n.uid AND ue.resource_id = rd.resource_id AND rd.name IN ('clothing','medicine','fertilizer');
