-- AI bot nations (app_core/bots). Bots are users rows with auth_type='bot';
-- these tables hold their profile and per-war state. Idempotent: the bot
-- Celery task also runs the same CREATE TABLE IF NOT EXISTS at startup.
CREATE TABLE IF NOT EXISTS bot_nations (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    archetype TEXT NOT NULL,
    tier TEXT NOT NULL,
    provinces INTEGER NOT NULL,
    population_per_province INTEGER NOT NULL,
    army_share DOUBLE PRECISION NOT NULL,
    target_strength BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_in_range_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS bot_war_state (
    war_id INTEGER PRIMARY KEY,
    last_attack_at DOUBLE PRECISION NOT NULL DEFAULT 0,
    attacks INTEGER NOT NULL DEFAULT 0,
    bot_guard_ts DOUBLE PRECISION NOT NULL DEFAULT 0,
    human_action_ts DOUBLE PRECISION NOT NULL DEFAULT 0
);
