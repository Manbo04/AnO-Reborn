-- "Safe Personal Deposit": a coalition member can opt in to keep their personal
-- bank balance (col_bank_contributions) out of reach of banker withdrawals.
CREATE TABLE IF NOT EXISTS col_deposit_protection (
    coalition_id INTEGER NOT NULL,
    user_id      INTEGER NOT NULL,
    enabled      BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (coalition_id, user_id)
);
