-- Bombers that flew air support cannot also fly an air attack in the same
-- UTC hour (wars/bomber_commit.py). One row per order, summed per user/hour.
CREATE TABLE IF NOT EXISTS bomber_sorties (
    id SERIAL PRIMARY KEY,
    war_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    hour_bucket BIGINT NOT NULL,
    role VARCHAR(16) NOT NULL,
    amount INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_bomber_sorties_user_hour
    ON bomber_sorties (user_id, hour_bucket);
