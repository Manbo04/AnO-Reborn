-- Civilian damage cap per Fire All salvo (flag nuke_salvo_civilian_cap, ships OFF).
-- While ON: one salvo may kill at most 25% of the target nation's people (fallout deaths
-- included) and destroy at most 25% of its buildings and 25% of its cities. A single
-- warhead is never weakened (cap = max(25%, first warhead)). See wars/salvo_cap.py.
BEGIN;

INSERT INTO feature_flags (key, enabled, rollout_percent, description, rollback_trigger)
VALUES ('nuke_salvo_civilian_cap', FALSE, 100,
        'ON = one nuclear Fire All salvo (also retaliation and auto-retaliation) kills at most 25% of the target nation''s people and destroys at most 25% of its buildings and cities in total; a single warhead is never weakened and warheads cut to zero stay in stock. OFF (default) = normal behaviour.',
        'Turn OFF if a salvo errors, or if nukes feel useless (Fire All against a nation with as many provinces as the attacker has nukes never reaches the cap). Nothing owned is removed; flipping the flag restores the old damage at once.')
ON CONFLICT (key) DO NOTHING;

COMMIT;
