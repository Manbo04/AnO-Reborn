-- Yearly Halloween gift (app_core/halloween.py): one claim per player per year.
CREATE TABLE IF NOT EXISTS halloween_gift_claims (
    user_id    INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    year       INTEGER     NOT NULL,
    amount     BIGINT      NOT NULL,
    claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, year)
);
