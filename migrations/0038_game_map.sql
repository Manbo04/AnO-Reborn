-- Migration 0038: Interactive Game Map - Unit Deployments
-- Creates the table for tracking military unit deployments on the strategic hex map

BEGIN;

CREATE TABLE IF NOT EXISTS map_unit_deployments (
    id SERIAL PRIMARY KEY,
    province_id INTEGER NOT NULL REFERENCES provinces(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    soldiers INTEGER NOT NULL DEFAULT 0 CHECK (soldiers >= 0),
    deployed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(province_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_map_deployments_province_id ON map_unit_deployments(province_id);
CREATE INDEX IF NOT EXISTS idx_map_deployments_user_id ON map_unit_deployments(user_id);

-- Log table for map combat events (for the event feed)
CREATE TABLE IF NOT EXISTS map_combat_log (
    id SERIAL PRIMARY KEY,
    attacker_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    defender_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    province_id INTEGER NOT NULL REFERENCES provinces(id) ON DELETE CASCADE,
    attacker_soldiers INTEGER NOT NULL DEFAULT 0,
    defender_soldiers INTEGER NOT NULL DEFAULT 0,
    result VARCHAR(20) NOT NULL DEFAULT 'attacker_won', -- 'attacker_won', 'defender_won'
    occurred_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_map_combat_log_province_id ON map_combat_log(province_id);
CREATE INDEX IF NOT EXISTS idx_map_combat_log_occurred_at ON map_combat_log(occurred_at DESC);

COMMIT;
