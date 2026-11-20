-- Sell-back haircut (flag ledger_sellback_haircut, ships ON by Dede's decision 2026-11-20).
-- The code in app_core/military/services.py already reads this flag, but no migration ever
-- created it, so it was off everywhere. While ON, selling a unit returns 50% of its gold and
-- resources (variables.LEDGER_SELLBACK_PERCENT) instead of 100%, which closes the sell the
-- army, hit a smaller target, rebuy for free loop.
BEGIN;

INSERT INTO feature_flags (key, enabled, rollout_percent, description, rollback_trigger)
VALUES ('ledger_sellback_haircut', TRUE, 100,
        'ON = selling a military unit returns 50% of its gold and resources (LEDGER_SELLBACK_PERCENT) instead of everything. OFF = full refund (old behaviour, allows the sell-back loop).',
        'Turn OFF if players report sells returning the wrong amount or the sell route erroring. Nothing owned is removed; flipping the flag restores the full refund at once.')
ON CONFLICT (key) DO NOTHING;

COMMIT;
