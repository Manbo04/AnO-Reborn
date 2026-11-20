-- Military upkeep v2 comes back behind a flag, with a raid fix (both ship ON by Dede's decision
-- 2026-11-20). Reverted 2026-11-07 because of raids: buy after the upkeep tick, hit, sell back
-- before the next tick, so the army never paid.
--
-- military_upkeep_v2: ON = v2 upkeep is charged (app_core/economy/military_upkeep_v2.py).
--   OFF = legacy per-unit upkeep, immediately, without another revert.
-- unit_sell_lock: ON = units bought in the last 2 hours (SELL_LOCK_HOURS) cannot be sold back.
--   Upkeep runs hourly, so every unit pays at least one tick before it can be sold.
BEGIN;

ALTER TABLE user_military ADD COLUMN IF NOT EXISTS last_bought_at timestamptz;

INSERT INTO feature_flags (key, enabled, rollout_percent, description, rollback_trigger)
VALUES ('military_upkeep_v2', TRUE, 100,
        'ON = military upkeep v2 (per unit, per game year, 1/24 charged each hourly tick, gold plus resources). OFF = legacy per-unit upkeep.',
        'Turn OFF if many nations cannot pay upkeep and armies stop working, or the tick errors. Nothing owned is removed; flipping the flag restores legacy upkeep at once.')
ON CONFLICT (key) DO NOTHING;

INSERT INTO feature_flags (key, enabled, rollout_percent, description, rollback_trigger)
VALUES ('unit_sell_lock', TRUE, 100,
        'ON = units bought in the last 2 hours cannot be sold back, so buy-after-the-upkeep-tick raids cannot dodge upkeep. OFF = units can be sold right after buying.',
        'Turn OFF if legitimate players are blocked from selling units they need to sell, or buying errors. Nothing owned is removed; flipping the flag lifts the lock at once.')
ON CONFLICT (key) DO NOTHING;

COMMIT;
