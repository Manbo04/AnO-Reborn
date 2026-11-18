-- Who can nuke whom (flag nuke_target_rules, ships OFF). While ON a nuclear launch (single
-- strike or the up-front gate of Fire All) is refused unless the target is inside the
-- population war range (75% to 133%) at launch time, has at least 100,000 influence and an
-- account at least 14 days old. Retaliation against the nation that nuked you in the same
-- war is always allowed. See wars/nuke_eligibility.py.
BEGIN;

INSERT INTO feature_flags (key, enabled, rollout_percent, description, rollback_trigger)
VALUES ('nuke_target_rules', FALSE, 100,
        'ON = a nuclear launch needs the target inside the population war range (75% to 133%) at launch time, with at least 100,000 influence and an account at least 14 days old; retaliation against whoever nuked you is always allowed. OFF (default) = normal behaviour (range only checked when the war was declared).',
        'Turn OFF if legitimate launches are refused by mistake (for example an in-range target reported as out of range or protected), or if nukes become unusable in real wars. Nothing owned is removed; flipping the flag restores the old behaviour at once.')
ON CONFLICT (key) DO NOTHING;

COMMIT;
