-- Feature flags / kill switch for the change pipeline (docs/CHANGE_PIPELINE.md, gate 5).
-- enabled = master switch (false means off for everyone). rollout_percent = share of nations
-- (deterministic by user id) that get the new behaviour while enabled.
CREATE TABLE IF NOT EXISTS feature_flags (
    key TEXT PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    rollout_percent INTEGER NOT NULL DEFAULT 100 CHECK (rollout_percent BETWEEN 0 AND 100),
    description TEXT NOT NULL DEFAULT '',
    rollback_trigger TEXT NOT NULL DEFAULT '',
    updated_by TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- No-op flag used to test the admin page and kill switch without touching game behaviour.
INSERT INTO feature_flags (key, enabled, rollout_percent, description, rollback_trigger)
VALUES ('pipeline_selftest', FALSE, 100,
        'Does nothing. Flip it to test the flags admin page.',
        'Never needed')
ON CONFLICT (key) DO NOTHING;
