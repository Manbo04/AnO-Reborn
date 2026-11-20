# Design: strategic airstrike limits (class D, flag `strategic_airstrike_limits`, ships OFF)

Decision owner: Dede. Part of the work that lets the `pause_missile_launches` flag end (the pause covers this strike because it only targets nuke infrastructure).

## 0. Problem and metric
Facts re-verified in `wars/routes.py` `strategic_airstrike` (read, and exercised by the new route tests):
* It spends no action points and has no cooldown. The bombers that survive come back, so it can be repeated at once. (`wars/action_points.py` even lists `"strategic_airstrike": (None, 0)`.)
* Silo target: `apply_building_damage(db, target, "silos", power, 15)`; power = surviving bombers x 0.7..1.3; one silo per 15 points; nothing caps the share.
* Tech target: power >= 50 sets `user_tech.is_unlocked = FALSE` for `nuclear_testing_facility`. There is no timer to bring it back; it has to be researched again.
* Only the defender's fighters (capacity fighters x 0.5..1.5) stop it.
* CORRECTION to my planning notes: the notes said this tech gates ICBMs and nukes. In code it zeroes the nuke BUY limit in `app_core/military/services.py` (`compute_display_limits`, line 87); ICBMs are gated by the separate `icbmsilo` upgrade there. With `nuke_rework` on, nukes come from the facility stockpile, and I found no NTF check on that path, so what the tech loss does under the rework is UNVERIFIED.

Metric: a strike spends action points, can take at most 25% of the target's silos, and removing the tech needs about three times today's bomber count.

## 1. Rule (flag ON)
* Costs `STRATEGIC_AIRSTRIKE_AP_COST` (2) air action points, the same as a drone strike. It is charged only after every check that can refuse the strike, so a refused strike is free. The AP regeneration is the cooldown (AP_START 6, AP_MAX 12, +1/hour per the constants in `wars/action_points.py`; the regeneration tick itself was not re-verified here).
* A strike destroys at most `STRATEGIC_AIRSTRIKE_MAX_SILO_SHARE` (25%) of the target's silos, and at least `STRATEGIC_AIRSTRIKE_MIN_SILOS_PER_STRIKE` (1) so a nation with 1 to 3 silos can still be hit.
* Tech loss needs `STRATEGIC_AIRSTRIKE_TECH_THRESHOLD` (150) points instead of 50 (`..._OFF` keeps today's number).

Code: `wars/airstrike_limits.py` (pure, constants, flag), `wars/routes.py` `strategic_airstrike`. Flag off: unchanged code path.

## 2. Numbers (before = OFF, after = ON)
Command: `ENVIRONMENT=DEV python scripts/sim_airstrike_limits.py` (the repo's constants and the new pure functions; power at the 1.0 midpoint; defender without fighters).

```
one strike, no fighters: silos destroyed (OFF today / ON)
 silos  bombers |   OFF   ON
     4       50 |     3    1
     4      150 |     4    1
     4      500 |     4    1
    10       50 |     3    2
    10      150 |    10    2
    10      500 |    10    2
    40       50 |     3    3
    40      150 |    10   10
    40      500 |    33   10
   100       50 |     3    3
   100      150 |    10   10
   100      500 |    33   25

strikes and waiting hours to destroy ALL silos (start with 6 air AP)
 silos  bombers |  OFF strikes/h |  ON strikes/h
    10      150 |         1/0    |        8/10  
    10      500 |         1/0    |        8/10  
    40      150 |         4/0    |       14/22  
    40      500 |         2/0    |       14/22  
   100      150 |        10/0    |       20/34  
   100      500 |         4/0    |       17/28  

Nuclear Testing Facility tech: lost at 50 points (about 50 surviving bombers) today, 150 with the flag
```

## 3. Constants (all in `wars/airstrike_limits.py`)
`STRATEGIC_AIRSTRIKE_AP_COST = 2`, `STRATEGIC_AIRSTRIKE_MAX_SILO_SHARE = 0.25`, `STRATEGIC_AIRSTRIKE_MIN_SILOS_PER_STRIKE = 1`, `STRATEGIC_AIRSTRIKE_TECH_THRESHOLD = 150` (flag on), `STRATEGIC_AIRSTRIKE_TECH_THRESHOLD_OFF = 50`.

## 4. Decisions that are Dede's
1. All five numbers above are suggested defaults.
2. Tech loss: I chose the least invasive option (a higher bar). It is still permanent. Making it temporary needs a new column or table (a migration, and db snapshot approval), so it is not built.
3. Whether a strike should cost air AP only, or also a cooldown timer.
4. Whether the strike should stay in the pause flag once these limits are on.
5. The minimum of 1 silo per strike (without it a nation with fewer than 4 silos could not be hit at all).

## 5. Exploit check (docs/templates/EXPLOIT_CHECKLIST.md)
* Timing, new account: Pass. Zero silos, zero bombers and a nation without the tech take the existing "found no" paths; refused and zero cases are covered by the route tests.
* Buy/sell/refund loops: Pass. Bombers still return when they survive; nothing is bought or refunded.
* Ledger: N/A. No gold or resources change.
* Hit-and-run and instant re-attack: Closed with the flag on: the third strike in a row empties the 6 starting AP and the fourth is refused (tested).
* Drain-then-strike: The AP spent are AIR AP, shared with drone strikes and recon flights, so an attacker has to choose between them (same pool as the drone strike). Only the attacker pays; the defender's AP are not touched.
* Special weapons supply and morale: Open, unchanged (bombers return).
* Abuse pushed to drones: Drone strikes also cost 2 air AP and can target silos (`STRIKE_TARGET_THRESHOLDS` "silo": 15), so a nation with many drones can still hit silos. B12 (a share cap on drone and cruise missile building damage) is the matching fix. The drone activation price quoted in my planning notes is unverified.
* Alts, self-targeting: Unchanged (self-target refused, active war required).
* Inputs: Pass. Zero or negative bomber counts are refused as before; the cap function is tested on random inputs.
* Double submit, races: Unchanged (same per-attacker advisory lock).
* Visibility: The AP error is the existing "Not enough air action points (have X, need 2). +1 every hour." The strike form does not show the new AP cost yet (UI not changed here).

## 6. Rollback
Turn the flag off at /admin/flags. Trigger: strategic airstrikes become useless (a big fleet cannot touch nuke infrastructure) or a strike errors. Nothing owned is removed.
