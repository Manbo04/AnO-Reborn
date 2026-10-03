-- 0102_personal_bank_accounts.sql
-- Personal bank accounts for coalition members (JoshMD suggestion):
-- Members can deposit resources into the alliance bank and withdraw up to their
-- personal deposited balance without needing banker approval.

ALTER TABLE col_bank_contributions ADD COLUMN IF NOT EXISTS total_withdrawn BIGINT DEFAULT 0;
