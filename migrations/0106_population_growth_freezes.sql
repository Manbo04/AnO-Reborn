-- 0106: Population/war rebalance (2026-10-04, agreed with The_kaiser in staff-chat).
-- A nation that loses a battle (12h) or is nuked (24h) gets no population
-- growth until frozen_until. Read by app_core/game_ticks/population.py,
-- written by wars/aftermath.py. Idempotent.
CREATE TABLE IF NOT EXISTS population_growth_freezes (
    user_id      INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    frozen_until TIMESTAMPTZ NOT NULL,
    reason       TEXT
);
