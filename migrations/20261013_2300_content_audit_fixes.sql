-- Content audit (2026-10-13): stop selling effect-less techs, fix lying tech
-- descriptions, fix a broken achievement icon, extend spy reports.
-- Re-runnable. Owners keep techs they already researched (user_tech is untouched,
-- no refunds); is_active only controls whether a tech can still be bought.

-- Techs 1-8 have no code anywhere that reads their effect. Their only
-- prerequisites are each other (2->4, 1->5, 4->6/7, 6->8), so no sold tech loses
-- its prerequisite chain. organized_supply_lines / large_storehouses were
-- already retired in 20261011_1900.
UPDATE tech_dictionary SET is_active = FALSE
WHERE name IN (
    'basic_agriculture', 'mining_techniques', 'military_doctrine', 'industrialization',
    'advanced_farming', 'scientific_method', 'steel_production', 'nuclear_physics',
    'organized_supply_lines', 'large_storehouses'
);

UPDATE tech_dictionary SET description =
    'Prerequisite for the ICBM Silo. It has no effect on its own.'
WHERE name = 'ballistic_missile_silo';
UPDATE tech_dictionary SET description =
    'Nuclear testing facilities give countries the ability to create nuclear warheads.'
WHERE name = 'nuclear_testing_facility';

-- fa-chart-line-down does not exist in Font Awesome 5.8.2 (blank icon).
UPDATE achievements SET icon = 'fa-chart-line' WHERE key = 'fun_debt';

-- Spy "units" reports also reveal these (NULL = never revealed, shown as "?").
ALTER TABLE spyinfo ADD COLUMN IF NOT EXISTS counter_intel_agents BIGINT;
ALTER TABLE spyinfo ADD COLUMN IF NOT EXISTS aircraft_carriers BIGINT;
ALTER TABLE spyinfo ADD COLUMN IF NOT EXISTS kamikaze_drones BIGINT;
ALTER TABLE spyinfo ADD COLUMN IF NOT EXISTS cruise_missiles BIGINT;
