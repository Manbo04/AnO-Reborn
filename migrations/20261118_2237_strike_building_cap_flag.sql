-- Limits on how many buildings one drone or cruise missile strike destroys (flag
-- strike_building_cap, ships OFF). While ON one strike destroys at most the smallest of:
-- 25% of the target's buildings of the chosen type (10% for silos), what is left of that
-- share in a 72h window (read from war_building_losses), and buildings worth 20x the
-- activation gold of the units committed. See wars/strike_building_cap.py.
BEGIN;

-- The 72h window total is read from the war history log by victim and building.
CREATE INDEX IF NOT EXISTS idx_war_building_losses_victim
    ON war_building_losses (victim_id, building, created_at DESC);

INSERT INTO feature_flags (key, enabled, rollout_percent, description, rollback_trigger)
VALUES ('strike_building_cap', FALSE, 100,
        'ON = one kamikaze drone or cruise missile strike destroys at most the smallest of: 25% of the target''s buildings of the chosen type (10% for silos), what is left of that share in a 72h window, and buildings worth 20x the activation gold of the units sent. OFF (default) = normal behaviour (no limits). Strategic airstrikes and population strikes are not affected.',
        'Turn OFF if drone and cruise missile strikes stop being worth their cost against normal-sized targets or a strike errors. Nothing owned is removed; flipping the flag restores the old damage at once.')
ON CONFLICT (key) DO NOTHING;

COMMIT;
