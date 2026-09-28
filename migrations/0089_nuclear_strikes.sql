-- 0089: Nuclear strike rework (2026-09-27).
-- A nuke now hits ONE attacker-chosen province. Every launch is logged here:
--   * repeat strikes on the same province within 72h get diminishing damage
--     (wars/nuclear.py reads recent rows by province_id),
--   * the launcher's influence penalty (influence_cost) decays linearly to 0
--     by recovers_at (7 days) and is subtracted by influence_formula.py,
--   * retaliation (cheaper strike) = the enemy nuked you first in this war.
-- Idempotent.
CREATE TABLE IF NOT EXISTS nuclear_strikes (
    id               BIGSERIAL PRIMARY KEY,
    war_id           INTEGER,
    attacker_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    target_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    province_id      INTEGER NOT NULL,
    province_name    TEXT,
    launched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    recovers_at      TIMESTAMPTZ NOT NULL,
    is_retaliation   BOOLEAN NOT NULL DEFAULT FALSE,
    influence_before BIGINT NOT NULL DEFAULT 0,
    influence_cost   BIGINT NOT NULL DEFAULT 0 CHECK (influence_cost >= 0),
    damage_multiplier NUMERIC(6, 4) NOT NULL DEFAULT 1,
    deaths           BIGINT NOT NULL DEFAULT 0,
    cities_destroyed INTEGER NOT NULL DEFAULT 0,
    buildings_destroyed INTEGER NOT NULL DEFAULT 0,
    happiness_lost   INTEGER NOT NULL DEFAULT 0
);

-- influence_formula: live penalty per launcher (recent rows only)
CREATE INDEX IF NOT EXISTS idx_nuclear_strikes_attacker_time
    ON nuclear_strikes (attacker_id, launched_at DESC);
-- repeat-strike decay per province
CREATE INDEX IF NOT EXISTS idx_nuclear_strikes_province_time
    ON nuclear_strikes (province_id, launched_at DESC);
-- retaliation lookup per war
CREATE INDEX IF NOT EXISTS idx_nuclear_strikes_war
    ON nuclear_strikes (war_id, launched_at);
