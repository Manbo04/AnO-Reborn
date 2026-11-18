-- Temporary pause on missile launches (flag pause_missile_launches, ships OFF).
-- While ON: nuclear strikes (single, Fire All and auto-retaliation), ICBM strikes, cruise
-- missile strikes and strategic airstrikes are refused. Producing, activating and owning missiles is unchanged and
-- nothing is spent or removed. See app_core/missile_pause.py.
BEGIN;

INSERT INTO feature_flags (key, enabled, rollout_percent, description, rollback_trigger)
VALUES ('pause_missile_launches', FALSE, 100,
        'ON = pause all nuke, ICBM, cruise missile and strategic airstrike launches while their balance is fixed. OFF (default) = normal behaviour. Turn on at /admin/flags and announce why and until when.',
        'Turn OFF as soon as the balance fix ships or if players cannot defend themselves because attackers use other weapons during the pause. Nothing owned is removed while paused.')
ON CONFLICT (key) DO NOTHING;

COMMIT;

