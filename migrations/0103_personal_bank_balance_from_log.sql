-- 0103_personal_bank_balance_from_log.sql
-- Fix double-withdraw exploit in personal bank accounts (0102).
-- total_deposited is a lifetime total since 2026-07-01, but banker-approved
-- payouts never decremented it, so members could withdraw deposits they had
-- already been paid back. Rebase each member's withdrawable balance on the
-- transaction log (since 2026-08-30), which records both directions:
--   available = max(0, logged deposits - logged withdrawals), capped at total_deposited.
ALTER TABLE col_bank_contributions ADD COLUMN IF NOT EXISTS total_withdrawn BIGINT DEFAULT 0;

UPDATE col_bank_contributions c
SET total_withdrawn = c.total_deposited - LEAST(
    c.total_deposited,
    GREATEST(0, COALESCE((
        SELECT SUM(CASE WHEN t.direction = 'deposit' THEN t.amount ELSE -t.amount END)
        FROM col_bank_transactions t
        WHERE t.coalition_id = c.coalition_id
          AND t.user_id = c.user_id
          AND t.resource = c.resource
    ), 0))
);
