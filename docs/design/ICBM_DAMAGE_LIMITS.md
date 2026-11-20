# Design: ICBM unit-destruction limits (class D, flag `icbm_damage_limits`, ships OFF)

Decision owner: Dede. Part of the work that lets the `pause_missile_launches` flag end. Source: player report "2 ICBMs took out my 50 destroyers".

## 0. Problem and metric
Facts re-verified in code (not from the planning notes):
* ICBM strikes go through `Military.special_fight` (attack_scripts/Nations.py), called from `wars/routes.py` `_resolve_special_attack`, not through the normal fight path.
* `units.IcbmUnit.attack` returns `[1000 * fired, bonus]`, then `special_fight` multiplies by `fired` AGAIN: destruction = rate x (damage / (1 + bonus)) x fired, rate random 0.3 to 0.5. So the loss grows with the square of the missiles fired.
* The only limit is what the target owns (`Units.casualties` caps at the stack size). The old comment about dividing by 20 is not in the code.
* NEW finding: against submarines `IcbmUnit.attack` returns bonus -5 per missile, so `1 + bonus` is negative and the destruction is NEGATIVE. `Units.casualties` then ADDS submarines (confirmed in code and by a real-database test). That is almost certainly not intended. Whether the sign was meant to make submarines harder to hit is unverified.
* Iron Dome interception already scales the damage by the surviving share (once).
Metric: growth is linear in missiles fired; a barrage destroys at most max(25% of the stack, what one missile destroys); a strike never adds units; ONE ICBM is never weakened (round 2: it keeps today's effect even on a small stack).

## 1. Rule (flag ON, ICBMs only)
(a) Linear: the number fired is multiplied in once. (b) Cap: at most `max(ICBM_MAX_UNIT_SHARE x units the target owns, what one missile would destroy)`, the same rule as the nuke salvo cap (round 2), so a single ICBM is not weakened and only extra missiles are limited. The target's stack is measured before the strike (floor, as casualties do). (c) The divisor `1 + bonus` is floored at `ICBM_MIN_DIVISOR` (1), so no negative destruction. Iron Dome survivors scale the damage before the cap. Nukes, infrastructure damage and every other fight are unchanged. Infrastructure damage from an ICBM (public works) is not changed.
Code: `app_core/military/icbm_damage.py` (pure, constants, flag), call in `attack_scripts/Nations.py` `special_fight`.

## 2. Numbers (before = OFF, after = ON)
Command: `ENVIRONMENT=DEV python scripts/sim_icbm_damage.py` (real `IcbmUnit.attack` plus the two pure functions; no Iron Dome).

```
share cap 25%; units destroyed, rate 0.3 to 0.5
target stack  ICBMs |      OFF (today) |               ON
          50      1 |      50 to 50     |      50 to 50    
          50      2 |      50 to 50     |      50 to 50    
          50      5 |      50 to 50     |      50 to 50    
          50     10 |      50 to 50     |      50 to 50    
         500      1 |     300 to 500    |     300 to 500   
         500      2 |     500 to 500    |     300 to 500   
         500      5 |     500 to 500    |     300 to 500   
         500     10 |     500 to 500    |     300 to 500   
        5000      1 |     300 to 500    |     300 to 500   
        5000      2 |    1200 to 2000   |     600 to 1000  
        5000      5 |    5000 to 5000   |    1250 to 1250  
        5000     10 |    5000 to 5000   |    1250 to 1250  

ICBMs at submarines (stack 500), rate 0.4:
  1 ICBM(s): OFF -100 (negative = submarines ADDED), ON 400
  2 ICBM(s): OFF -178 (negative = submarines ADDED), ON 400
  5 ICBM(s): OFF -417 (negative = submarines ADDED), ON 400
```

## 3. Constants (all in `app_core/military/icbm_damage.py`)
`ICBM_MAX_UNIT_SHARE = 0.25`, `ICBM_MIN_DIVISOR = 1.0`.

## 4. Decisions that are Dede's
1. The 25% share (suggested default). With the single-missile floor the share only bites on stacks above about 1,600 units (one missile destroys 300 to 500: rate 0.3 to 0.5 x 1,000). On small stacks the main effect is linear instead of squared growth, and the original report is NOT fixed there: 1 ICBM already destroys a 50-unit fleet today (the report said 2) and still does with the flag. If small stacks must be protected, the single-missile floor has to go (then 1 ICBM at 50 units destroys 12), which weakens a lone missile. That trade-off is Dede's.
2. Whether to keep linear growth AND the cap, or only one of them.
3. Submarines: treat like any other target (implemented), or make them harder to hit on purpose. The old behaviour (adding units) is clearly a bug.
4. With stacks under 4 units the cap rounds to 0 and the strike destroys nothing.
5. Unit recovery protection after a hit (option d in the notes) is not built.

## 5. Exploit check (docs/templates/EXPLOIT_CHECKLIST.md)
* Timing, tick, truce, new account: Pass. No timing input; zero stacks give zero.
* Buy/sell/refund loops: Pass. Nothing is bought or refunded; the missile is spent as before.
* Ledger: N/A. No gold or resource change (units are updated by the existing casualty code).
* Special weapons supply and morale: Open, unchanged (ICBMs still spend no supply).
* Drain-then-strike: Pass for ICBMs: the cap is on the share of the target's stack, so repeated ICBM strikes can still erode a stack by 25% each time (the cap is per strike, not per war). Recovery protection (option d) would close that; not built.
* Abuse pushed to drones: Checked in code, no new path: drone strikes target buildings and population; their only effect on units is a 10% chance per strike to kill up to as many soldiers as the drones hit (wars/routes.py `drone_strike`, read, not run). So capping ICBM unit losses does not make drones a better tool against unit stacks.
* Alts, self-targeting, hidden nations: Same route and checks as before.
* Inputs: Pass. Zero fired, zero owned, surviving outside 0..1 and negative bonus are handled and tested over a parameter grid.
* Double submit, races: Unchanged (the existing `_claim_attack_slot` gate).
* Visibility: The war result page shows the units destroyed as before; no new text.

## 6. Rollback
Turn the flag off at /admin/flags. Trigger: ICBM strikes on normal stacks destroy almost nothing (players stop using them), or a strike errors. Nothing owned is removed.
