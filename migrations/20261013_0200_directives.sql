-- National directives: 7-day boosts a player activates for a gold fee.
-- One row per (nation, directive); an expired row is overwritten on re-activation.
CREATE TABLE IF NOT EXISTS directives (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    directive_key TEXT NOT NULL,
    activated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (user_id, directive_key)
);
CREATE INDEX IF NOT EXISTS directives_active_idx ON directives (expires_at);
