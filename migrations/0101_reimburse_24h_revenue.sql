-- 0101_reimburse_24h_revenue.sql
-- Table to record idempotent player reimbursements and reset tax_income cursor.

CREATE TABLE IF NOT EXISTS player_reimbursements (
    reimbursement_id TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    total_gold_distributed BIGINT,
    users_reimbursed INT,
    details JSONB
);

-- Ensure task_cursors has last_id=0 for tax_income
INSERT INTO task_cursors (task_name, last_id)
VALUES ('tax_income', 0)
ON CONFLICT (task_name) DO UPDATE SET last_id = 0;
