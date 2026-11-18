-- Cap on the share of one building type a drone or cruise missile strike destroys
-- (flag strike_building_cap, ships OFF). While ON one strike destroys at most 25% of the
-- target's buildings of the chosen type (at least 1). See wars/strike_building_cap.py.
BEGIN;

INSERT INTO feature_flags (key, enabled, rollout_percent, description, rollback_trigger)
VALUES ('strike_building_cap', FALSE, 100,
        'ON = one kamikaze drone or cruise missile strike destroys at most 25% of the target''s buildings of the chosen type (at least 1). OFF (default) = normal behaviour (no share cap). Strategic airstrikes and population strikes are not affected.',
        'Turn OFF if drone and cruise missile strikes stop being worth their cost against normal-sized targets or a strike errors. Nothing owned is removed; flipping the flag restores the old damage at once.')
ON CONFLICT (key) DO NOTHING;

COMMIT;
