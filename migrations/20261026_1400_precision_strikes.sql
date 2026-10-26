-- Balance prototype phase 4: precision strikes (wars/precision.py).
-- Log used for the per-war daily limit, diminishing returns per target type,
-- and the one-shot disruption applied to the striker's next attack.
CREATE TABLE IF NOT EXISTS precision_strikes (
    id SERIAL PRIMARY KEY,
    war_id INTEGER NOT NULL,
    attacker_id INTEGER NOT NULL,
    target_id INTEGER NOT NULL,
    striker VARCHAR(20) NOT NULL,
    target_unit VARCHAR(20) NOT NULL,
    killed INTEGER NOT NULL DEFAULT 0,
    lost INTEGER NOT NULL DEFAULT 0,
    suppress REAL NOT NULL DEFAULT 0,
    consumed BOOLEAN NOT NULL DEFAULT FALSE,
    struck_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_precision_strikes_war_attacker
    ON precision_strikes (war_id, attacker_id, struck_at);
