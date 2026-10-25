-- War rules overhaul (wars/rules.py).
-- origin: 'declared' or 'mdp_join' (an ally's counter-attack, not offensive).
ALTER TABLE wars ADD COLUMN IF NOT EXISTS origin VARCHAR(20) NOT NULL DEFAULT 'declared';
ALTER TABLE wars ADD COLUMN IF NOT EXISTS parent_war_id INTEGER;
-- One nuke volley per side per war (set on launch, intercepted or not).
ALTER TABLE wars ADD COLUMN IF NOT EXISTS attacker_nuked BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE wars ADD COLUMN IF NOT EXISTS defender_nuked BOOLEAN NOT NULL DEFAULT FALSE;

-- A pending surrender offer (one per war); the other side accepts/rejects.
CREATE TABLE IF NOT EXISTS surrender_offers (
    war_id INTEGER PRIMARY KEY,
    surrendering_id INTEGER NOT NULL,
    kind VARCHAR(16) NOT NULL CHECK (kind IN ('conditional', 'unconditional')),
    created_at DOUBLE PRECISION NOT NULL
);

-- Temporary post-war penalties (unconditional surrender military cap).
CREATE TABLE IF NOT EXISTS war_penalties (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    war_id INTEGER,
    kind VARCHAR(32) NOT NULL,
    factor DOUBLE PRECISION NOT NULL,
    created_at DOUBLE PRECISION NOT NULL,
    expires_at DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_war_penalties_user_expires
    ON war_penalties (user_id, expires_at);
