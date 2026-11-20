-- Lower end-of-war spoils (flag war_spoils_reduced, ships OFF; Dede turns it on at /admin/flags).
-- Today a war winner takes 20% of every resource the loser holds (30% with Looting Teams), and
-- the truce between wars is 3 days, so a nation can live off winning wars and never build.
-- While ON: 12% standard, 18% with Looting Teams. A conditional surrender stays at 10%.
-- The numbers are placeholders in wars/rules.py (REDUCED_STANDARD_SPOILS, REDUCED_LOOTING_TEAMS_SPOILS).
BEGIN;

INSERT INTO feature_flags (key, enabled, rollout_percent, description, rollback_trigger)
VALUES ('war_spoils_reduced', FALSE, 100,
        'ON = the winner of a war takes 12% of every resource the loser holds (18% with Looting Teams) instead of 20% (30%). A conditional surrender stays at 10%, an unconditional one pays the full standard rate. OFF (default) = 20% / 30%.',
        'Turn OFF if wars stop being worth fighting (nobody declares) or war-end errors. Nothing owned is removed; flipping the flag restores the old rates for the next war that ends.')
ON CONFLICT (key) DO NOTHING;

COMMIT;
