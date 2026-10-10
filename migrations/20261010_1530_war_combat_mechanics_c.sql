-- Migration: 20261010_1530_war_combat_mechanics_c.sql
-- JOB C: branch action points, entrenchment, intel, naval blockade

-- C1: Action points per branch per side (ground, air, naval)
ALTER TABLE wars ADD COLUMN IF NOT EXISTS attacker_ground_ap INTEGER NOT NULL DEFAULT 6;
ALTER TABLE wars ADD COLUMN IF NOT EXISTS attacker_air_ap INTEGER NOT NULL DEFAULT 6;
ALTER TABLE wars ADD COLUMN IF NOT EXISTS attacker_naval_ap INTEGER NOT NULL DEFAULT 6;
ALTER TABLE wars ADD COLUMN IF NOT EXISTS defender_ground_ap INTEGER NOT NULL DEFAULT 6;
ALTER TABLE wars ADD COLUMN IF NOT EXISTS defender_air_ap INTEGER NOT NULL DEFAULT 6;
ALTER TABLE wars ADD COLUMN IF NOT EXISTS defender_naval_ap INTEGER NOT NULL DEFAULT 6;

-- C2: Entrenchment levels per side (0..3)
ALTER TABLE wars ADD COLUMN IF NOT EXISTS attacker_entrench SMALLINT NOT NULL DEFAULT 0;
ALTER TABLE wars ADD COLUMN IF NOT EXISTS defender_entrench SMALLINT NOT NULL DEFAULT 0;

-- C3: Intel levels per side (0..100)
ALTER TABLE wars ADD COLUMN IF NOT EXISTS attacker_intel SMALLINT NOT NULL DEFAULT 0;
ALTER TABLE wars ADD COLUMN IF NOT EXISTS defender_intel SMALLINT NOT NULL DEFAULT 0;

-- C4: Naval blockade expiration timestamp per side
ALTER TABLE wars ADD COLUMN IF NOT EXISTS attacker_blockaded TIMESTAMPTZ NULL;
ALTER TABLE wars ADD COLUMN IF NOT EXISTS defender_blockaded TIMESTAMPTZ NULL;

COMMENT ON COLUMN wars.attacker_ground_ap IS 'Attacker ground action points (max 12, regens +1/hr)';
COMMENT ON COLUMN wars.attacker_air_ap IS 'Attacker air action points (max 12, regens +1/hr)';
COMMENT ON COLUMN wars.attacker_naval_ap IS 'Attacker naval action points (max 12, regens +1/hr)';
COMMENT ON COLUMN wars.defender_ground_ap IS 'Defender ground action points (max 12, regens +1/hr)';
COMMENT ON COLUMN wars.defender_air_ap IS 'Defender air action points (max 12, regens +1/hr)';
COMMENT ON COLUMN wars.defender_naval_ap IS 'Defender naval action points (max 12, regens +1/hr)';
COMMENT ON COLUMN wars.attacker_entrench IS 'Attacker entrenchment level (0..3, +10% ground defense per level)';
COMMENT ON COLUMN wars.defender_entrench IS 'Defender entrenchment level (0..3, +10% ground defense per level)';
COMMENT ON COLUMN wars.attacker_intel IS 'Attacker war intelligence level (0..100)';
COMMENT ON COLUMN wars.defender_intel IS 'Defender war intelligence level (0..100)';
COMMENT ON COLUMN wars.attacker_blockaded IS 'Attacker is blockaded until this timestamp (unable to trade/market)';
COMMENT ON COLUMN wars.defender_blockaded IS 'Defender is blockaded until this timestamp (unable to trade/market)';
