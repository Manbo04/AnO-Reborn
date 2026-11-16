-- Command Briefing: one-time resource top-up per step so a new nation is never
-- blocked by a missing resource it cannot find on the market (Dan90, 2026-11-16).
CREATE TABLE IF NOT EXISTS tour_supply (
    user_id integer NOT NULL,
    step_key text NOT NULL,
    granted jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, step_key)
);
