-- Migration: 0072 - Buff Aircraft Carrier offensive stat
-- Date: 2026-09-07
--
-- Discord (#military-recommendations, 2026-09-07): aircraft_carriers shipped
-- in migration 0066 with base_attack 3.0 -- far below every other naval unit
-- (next lowest, apaches, is 15.0; destroyers/fighters/submarines/bombers/
-- cruisers all sit between 35 and 55), making the unit a strict downgrade
-- with no offensive role. Dede approved bringing it up to the same tier as
-- destroyers (40.0) while leaving base_defense untouched.

BEGIN;

UPDATE unit_dictionary
SET base_attack = 40.0
WHERE name = 'aircraft_carriers';

COMMIT;
