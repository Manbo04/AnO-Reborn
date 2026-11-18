# Design: drone and cruise missile building cap (class D, flag `strike_building_cap`, ships OFF)

Decision owner: Dede. Part of the work that lets the `pause_missile_launches` flag end. Drones are NOT paused, so this matters most for them.

## 0. Problem and metric
Facts re-verified in code:
* `wars/service.py` `apply_building_damage` destroys `min(total owned, damage_points // threshold)` buildings of one type, taking from the biggest stack first. Nothing limits the share of the type.
* Drones (`wars/routes.py` `drone_strike`): hits = surviving drones x 0.5..0.9, 2 points per hit. Cruise missiles (`cruise_missile_strike`): 8 points per missile that gets past the Iron Dome. Points per building (`STRIKE_TARGET_THRESHOLDS`): silo 15, steel mills / component factories / aluminium refineries / oil refineries 10, farms, mines, fisheries and similar 6.
* Existing limits: 2 AP per strike (air for drones, naval for cruise missiles), population strikes capped at 2% (`POP_KILL_CAP_PER_STRIKE`), SAMs, fighters, apaches and Iron Domes intercept.
* Prices (variables.py): drone 3,500 gold and cruise missile 250,000 gold to activate, plus fuel; farm 1,500,000, steel mill 6,000,000, silo 350,000,000 gold to rebuild (gold only, buildings also need resources).
Metric: one strike destroys at most 25% of one building type; a strike that asks for less is unchanged.

## 1. Rule (flag ON)
`apply_building_damage(..., max_share=0.25)` is passed by `drone_strike` and `cruise_missile_strike` only. One strike destroys at most `STRIKE_BUILDING_MAX_SHARE` (25%) of the buildings of the chosen type the target owns across ALL provinces, and at least `STRIKE_BUILDING_MIN_PER_STRIKE` (1) when it owns any. The strategic airstrike (own limits, B11) and population strikes (existing 2% cap) are untouched. Flag off: `max_share` is None and the damage math is the same as before.
Code: `wars/strike_building_cap.py` (pure, constants, flag), `wars/service.py`, two call sites in `wars/routes.py`.

## 2. Numbers (before = OFF, after = ON)
Command: `ENVIRONMENT=DEV python scripts/sim_strike_building_cap.py` (full table, 45 rows). Midpoint rolls (70% of drones hit), no interception. Selected rows:

```
share cap 25%, min 1
  weapon  sent     building  owned |   OFF   ON |  activation gold  rebuild gold OFF  rebuild gold ON
  drones  1000        farms    200 |   200   50 |        3,500,000       300,000,000       75,000,000
  drones  1000        farms   1000 |   233  233 |        3,500,000       349,500,000      349,500,000
  drones  1000  steel_mills    200 |   140   50 |        3,500,000       840,000,000      300,000,000
  drones  1000  steel_mills   1000 |   140  140 |        3,500,000       840,000,000      840,000,000
  drones  1000        silos    200 |    93   50 |        3,500,000    32,550,000,000   17,500,000,000
  drones  1000        silos   1000 |    93   93 |        3,500,000    32,550,000,000   32,550,000,000
  cruise   100        farms     20 |    20    5 |       25,000,000        30,000,000        7,500,000
  cruise   100        farms    200 |   133   50 |       25,000,000       199,500,000       75,000,000
  cruise   100  steel_mills     20 |    20    5 |       25,000,000       120,000,000       30,000,000
  cruise   100  steel_mills    200 |    80   50 |       25,000,000       480,000,000      300,000,000
  cruise   100        silos     20 |    20    5 |       25,000,000     7,000,000,000    1,750,000,000
  cruise   100        silos    200 |    53   50 |       25,000,000    18,550,000,000   17,500,000,000
```

What the table shows:
* The cap only bites when a strike asks for more than 25% of what the target owns. Against a big stock (1,000 farms) 1,000 drones still destroy 233 (23%) with the flag on.
* So the cap bounds the worst case (a swarm wiping a whole type) but does NOT fix the price gap: 3.5M gold of drones destroys 233 farms that cost 349.5M gold to rebuild (about 100 to 1), flag or no flag. A recovery shield or a rebuild discount (N3) would be needed for that and is not built.
* Silos: a drone strike at silos is also capped at 25%, but silos cost 350M gold each, and drones are not paused. Until a stricter rule exists (for example a lower share for silos), drones remain the cheapest way to hit nuke infrastructure. This is the main thing for Dede to look at.

## 3. Constants (all in `wars/strike_building_cap.py`)
`STRIKE_BUILDING_MAX_SHARE = 0.25`, `STRIKE_BUILDING_MIN_PER_STRIKE = 1`.

## 4. Decisions that are Dede's
1. The 25% share (suggested), and whether silos (or other military buildings) get a lower share than farms and mines.
2. The minimum of 1 building per strike for tiny stocks.
3. Whether to add a recovery shield after a strike (not built).
4. `record_building_loss` is still called without a province (same gap as the war history work), so these losses cannot be shown per province.

## 5. Exploit check (docs/templates/EXPLOIT_CHECKLIST.md)
* Timing, new account: Pass. A target with none of the building is refused before anything is spent (existing `_target_has_building`); a stock of 1 to 3 still loses 1 (tested).
* Buy/sell/refund loops: Pass. Nothing is bought or refunded; drones and missiles are consumed as before.
* Ledger: N/A. No gold or resource change in this code (the existing gasoline spend still goes through `ledger.spend_resources`).
* Repeat strikes: Residual. The cap is per strike. With 2 AP per strike and 6 starting AP, three strikes in a row can still take about 58% of one type (1 - 0.75^3). Not closed here.
* Splitting stock over provinces to dodge the cap: Pass. The cap uses the nation-wide total (tested with 4 provinces).
* Abuse pushed to drones: This change applies to drones and cruise missiles equally, so it does not move damage from one to the other. The strategic airstrike keeps its own limits.
* Alts, self-targeting, hidden nations: Unchanged (same route checks).
* Inputs: Pass. Zero and negative damage, zero stock and huge counts are handled and tested over random inputs.
* Double submit, races: Unchanged (same per-attacker advisory lock).
* Visibility: The strike report text is unchanged, so a capped strike reads like a normal one ("destroyed N farms"). The attacker is not told the cap was hit (UI not changed here).

## 6. Rollback
Turn the flag off at /admin/flags. Trigger: drone and cruise missile strikes stop being worth their cost against normal-sized targets, or a strike errors. Nothing owned is removed.
