-- Strategic airstrike limits (flag strategic_airstrike_limits, ships OFF).
-- While ON: each strike costs 2 air action points, one strike destroys at most 25% of
-- the target's silos (at least 1), and destroying the Nuclear Testing Facility tech needs
-- 150 damage points instead of 50. See wars/airstrike_limits.py.
BEGIN;

INSERT INTO feature_flags (key, enabled, rollout_percent, description, rollback_trigger)
VALUES ('strategic_airstrike_limits', FALSE, 100,
        'ON = a strategic airstrike costs 2 air action points, destroys at most 25% of the target''s silos per strike (at least 1) and needs 150 damage points (not 50) to destroy the Nuclear Testing Facility tech. OFF (default) = normal behaviour (no action points, no cap, 50 points).',
        'Turn OFF if strategic airstrikes become useless (a strike with a large bomber fleet cannot touch nuke infrastructure) or a strike errors. Nothing owned is removed; flipping the flag restores the old behaviour at once.')
ON CONFLICT (key) DO NOTHING;

COMMIT;
