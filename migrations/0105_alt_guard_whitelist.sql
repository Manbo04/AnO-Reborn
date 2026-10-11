-- Staff whitelist for pairs of accounts that legitimately share an IP
-- (family, roommates). user_a < user_b always.
CREATE TABLE IF NOT EXISTS alt_guard_whitelist (
    user_a INTEGER NOT NULL,
    user_b INTEGER NOT NULL,
    PRIMARY KEY (user_a, user_b),
    CHECK (user_a < user_b)
);
