-- Migration: 0044 - Rebalance air/navy attack & defense stats
-- Date: 2026-08-19
-- Player feedback (Unknown Identity aka germanicusjuliuscaesar,
-- #military-recommendations, 2026-08-13): apaches (55/25) dwarfed fighters
-- (2/1.5), making air-force composition lopsided since apaches beat
-- soldiers/tanks/bombers/fighters while fighters only counter bombers.
-- Navy was flagged as underpowered relative to the firepower ships carry in
-- practice. Dede acknowledged the numbers needed updating in-thread but
-- never shipped it. This migration applies the suggested ranges (using the
-- midpoint where a range was given) to existing air/navy units only --
-- army (soldiers/tanks/artillery) was explicitly called out as fine and is
-- left untouched. New unit types (Strategic Bomber, Interceptor, Anti-Air
-- artillery, Anti-personnel tank, Frigates, Attack Submarine, Aircraft
-- Carrier) and the proposed logistics/supply-cap mechanic from the same
-- thread are NOT part of this migration -- separate scoping needed.

BEGIN;

-- Fighters: suggested 30-40 attack, 20-30 defense (was 2/1.5)
UPDATE unit_dictionary
SET base_attack  = 35,
    base_defense = 25
WHERE name = 'fighters';

-- Bombers: suggested 50 attack, 10 defense (was 3.5/1)
UPDATE unit_dictionary
SET base_attack  = 50,
    base_defense = 10
WHERE name = 'bombers';

-- Apaches: suggested 10-20 attack, 10 defense (was 55/25 -- the stat that
-- prompted the report; brought down in line with fighters/bombers)
UPDATE unit_dictionary
SET base_attack  = 15,
    base_defense = 10
WHERE name = 'apaches';

-- Destroyers: suggested 40 attack, 50-60 defense (was 2/2)
UPDATE unit_dictionary
SET base_attack  = 40,
    base_defense = 55
WHERE name = 'destroyers';

-- Cruisers: suggested 50-60 attack, 60-70 defense (was 2.5/2.5)
UPDATE unit_dictionary
SET base_attack  = 55,
    base_defense = 65
WHERE name = 'cruisers';

-- Submarines: suggested 50 attack, 20 defense (was 1.5/3)
UPDATE unit_dictionary
SET base_attack  = 50,
    base_defense = 20
WHERE name = 'submarines';

COMMIT;
