-- Tech descriptions that promised war-supply effects. The supply system was
-- replaced by action points, so make the text say what actually happens.
UPDATE tech_dictionary SET description = 'Looting teams strip resources from defeated enemies: when you win a war, you take 30% of the loser''s resources instead of 20%.' WHERE name = 'looting_teams';
UPDATE tech_dictionary SET description = 'No effect right now: war supplies were replaced by action points. A replacement effect will go to the community vote.' WHERE name IN ('organized_supply_lines', 'large_storehouses');
UPDATE tech_dictionary SET description = 'Use of propaganda in media, news and devices keeps citizens content (no unemployment happiness penalty) and brings the gold cost of recruiting soldiers down by 35%.' WHERE name = 'widespread_propaganda';
