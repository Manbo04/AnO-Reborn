-- Idempotency gate for /warResult's replay race (see wars/routes.py, fixed
-- 2026-09-23). wars.last_visited is a `real` (single-precision float)
-- column -- accurate to ~7 significant digits, but a Unix timestamp at
-- today's magnitude needs ~10, so it cannot reliably represent even a
-- 1-second time delta and can't be reused for a sub-window debounce check
-- (confirmed empirically: a real-column comparison intended to reject a
-- concurrent replay within 1 second instead behaved unpredictably due to
-- rounding). This adds a dedicated double-precision column solely for that
-- one-shot gate, leaving last_visited's existing informational use alone.

ALTER TABLE wars ADD COLUMN IF NOT EXISTS last_attack_resolved_at DOUBLE PRECISION;
