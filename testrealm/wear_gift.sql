-- Rollout step for ledger_wearout: one-time Machinery starter stock = 72 hours of full need for every nation with an industrial fleet.
WITH fleets AS (
  SELECT ub.user_id, SUM(ub.quantity) fleet FROM user_buildings ub JOIN building_dictionary bd USING(building_id)
  WHERE bd.name IN ('farms','pumpjacks','coal_mines','bauxite_mines','copper_mines','uranium_mines','lead_mines','iron_mines','lumber_mills','silver_mines','diamond_mines','bullion_mines','fisheries','component_factories','steel_mills','ammunition_factories','machinery_works','aluminium_refineries','oil_refineries')
  GROUP BY ub.user_id HAVING SUM(ub.quantity) > 0)
INSERT INTO user_economy (user_id, resource_id, quantity)
SELECT f.user_id, (SELECT resource_id FROM resource_dictionary WHERE name='machinery'), CEIL(f.fleet / 50.0) * 72 FROM fleets f
ON CONFLICT (user_id, resource_id) DO UPDATE SET quantity = user_economy.quantity + EXCLUDED.quantity;
