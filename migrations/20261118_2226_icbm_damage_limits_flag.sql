-- ICBM unit-destruction limits (flag icbm_damage_limits, ships OFF).
-- While ON: an ICBM strike destroys units linearly in the number fired (today it grows
-- with the square) and at most 25% of one unit type the target owns; a strike can no
-- longer ADD units (negative destruction against submarines). Only ICBMs. See
-- app_core/military/icbm_damage.py.
BEGIN;

INSERT INTO feature_flags (key, enabled, rollout_percent, description, rollback_trigger)
VALUES ('icbm_damage_limits', FALSE, 100,
        'ON = an ICBM strike destroys units linearly in the number fired and at most max(25% of one unit type the target owns, what one missile destroys), so a lone ICBM is not weakened (and never adds units). OFF (default) = normal behaviour (damage grows with the square of the missiles fired, no share cap).',
        'Turn OFF if ICBMs stop being worth their cost (a strike on a normal stack destroys almost nothing) or if a strike errors. Nothing owned is removed; flipping the flag restores the old damage at once.')
ON CONFLICT (key) DO NOTHING;

COMMIT;
