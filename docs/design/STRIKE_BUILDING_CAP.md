# Design: drone and cruise missile strike limits (class D, flag `strike_building_cap`, ships OFF)

Decision owner: Dede. Part of the work that lets the `pause_missile_launches` flag end. Drones are NOT paused, so this matters most for them. Round 2 added the gold-value cap, the lower silo share and the 72h window; round 1 only had a per-strike share cap, which does not touch the cost gap when the target stack is big.

## 0. Problem and metric
Facts re-verified in code:
* `wars/service.py` `apply_building_damage` destroys `min(total owned, damage_points // threshold)` buildings of one type, biggest stack first. Nothing limited the share, the value or repeats.
* Drones (`wars/routes.py` `drone_strike`): hits = surviving drones x 0.5..0.9, 2 points per hit. Cruise missiles (`cruise_missile_strike`): 8 points per missile past the Iron Dome. Points per building (`STRIKE_TARGET_THRESHOLDS`): silo 15, steel mills and other refineries/factories 10, farms, mines, fisheries 6.
* Existing limits: 2 AP per strike (air for drones, naval for cruise missiles), population strikes capped at 2% (`POP_KILL_CAP_PER_STRIKE`), SAMs, fighters, apaches and Iron Domes.
* Prices (variables.py): activation gold `MILDICT` drone 3,500, cruise missile 250,000 (`process_activate_units` charges `price x count`, no discount). Rebuild gold: `PROVINCE_UNIT_PRICES` via `app_core/economy/building_costs.py get_build_cost`: farm 1,500,000, steel mill 6,000,000, silo 350,000,000 (before the victim's policy discount, and without the resources a rebuild also needs).
Metric (the one the user asked for): gold value destroyed per gold of weapons spent ("ratio"). Today, at midpoint rolls and no interception: drones at farms 99.9x, at steel mills 240x, at silos 9,300x; cruise missiles at farms 8x, steel mills 19.2x, silos 742x (section 3). Target: the default closes the outliers (drones, silos) and leaves the pricier cruise missiles at farms and steel mills as they are.

## 1. Rule (flag ON)
One flag, not two: the share cap alone leaves the cost gap open, so a separate flag would let a half fix ship by itself. Every part is a named constant and can be tuned separately.
`apply_building_damage(..., limits=StrikeLimits)` is given limits by `drone_strike` and `cruise_missile_strike` only. One strike destroys the smallest of:
1. what the damage points ask for (unchanged);
2. SHARE: `STRIKE_BUILDING_MAX_SHARE` (25%) of the building type the target owns across all provinces, `STRIKE_SILO_MAX_SHARE` (10%) for silos; at least `STRIKE_BUILDING_MIN_PER_STRIKE` (1) on the first strike in a window so a stock of 1 to 3 can be hit;
3. WINDOW: strikes together may destroy at most that share of what the target had at the start of the `STRIKE_WINDOW_HOURS` (72h) window (owned now plus destroyed by strikes in the window), so repeated strikes cannot erode a type;
4. VALUE: `floor(STRIKE_VALUE_CAP_MULTIPLE (20) x activation gold of the units sent / rebuild gold of one building)`. Units sent = every drone or missile committed, before interception. The minimum of one does NOT override this cap (a drone cannot level a 350M silo).
The strategic airstrike (own limits, B11) and population strikes (existing 2% cap) are untouched. Flag off: `limits` is None and the damage math is the same as before, with no extra queries.
Code: `wars/strike_building_cap.py` (pure functions, constants, thin DB readers), `wars/service.py`, two call sites in `wars/routes.py`.

## 2. Window total: can `war_building_losses` supply it? Yes, no new table
`wars/history.py record_building_loss` writes one row (war_id, victim_id, building, quantity, source, created_at) per destroyed batch, and `apply_building_damage` calls it with source `'strike'` for every strike (drones, cruise missiles and the strategic airstrike). The window total is `SUM(quantity) WHERE victim_id AND building AND source='strike' AND created_at > now() - 72h`. Caveats:
* The log is best effort (it never raises and skips the insert on error), so a failed insert undercounts; the reader also returns 0 on any error, with a savepoint so the strike's transaction stays usable.
* It only logs while the victim has a war without a peace date, which is always true for a strike (a strike needs an active war).
* The existing index is on `(war_id, created_at)`, not victim, so the flag migration adds `idx_war_building_losses_victim (victim_id, building, created_at DESC)`. The table is not in the `db/schema.sql` snapshot (it came from migration 20261027_2000), so no `db/` change is needed here.
* Strategic airstrike silo losses count toward the window too (same function), which is intended.

## 3. Numbers (before = OFF, after = ON for K = 5, 10, 20, 50)
Command: `ENVIRONMENT=DEV python scripts/sim_strike_building_cap.py` (repo constants, `get_build_cost` prices and the pure functions; midpoint rolls, no interception, first strike in the window).

```
share 25% (silos 10%), window 72h, min 1; value cap K in (5, 10, 20, 50) (default 20)
cell = buildings destroyed (ratio = rebuild gold / gold of units sent)
 weapon  sent    building owned |            OFF |            K=5 |           K=10 |           K=20 |           K=50
 drones   100       farms   200 |    23 (  98.6x) |     1 (  4.3x) |     2 (  8.6x) |     4 ( 17.1x) |    11 ( 47.1x)
 drones  1000       farms   200 |   200 (  85.7x) |    11 (  4.7x) |    23 (  9.9x) |    46 ( 19.7x) |    50 ( 21.4x)
 drones  5000       farms   200 |   200 (  17.1x) |    50 (  4.3x) |    50 (  4.3x) |    50 (  4.3x) |    50 (  4.3x)
 drones   100       farms  1000 |    23 (  98.6x) |     1 (  4.3x) |     2 (  8.6x) |     4 ( 17.1x) |    11 ( 47.1x)
 drones  1000       farms  1000 |   233 (  99.9x) |    11 (  4.7x) |    23 (  9.9x) |    46 ( 19.7x) |   116 ( 49.7x)
 drones  5000       farms  1000 |  1000 (  85.7x) |    58 (  5.0x) |   116 (  9.9x) |   233 ( 20.0x) |   250 ( 21.4x)
 drones   100 steel_mills   200 |    14 ( 240.0x) |     0 (  0.0x) |     0 (  0.0x) |     1 ( 17.1x) |     2 ( 34.3x)
 drones  1000 steel_mills   200 |   140 ( 240.0x) |     2 (  3.4x) |     5 (  8.6x) |    11 ( 18.9x) |    29 ( 49.7x)
 drones  5000 steel_mills   200 |   200 (  68.6x) |    14 (  4.8x) |    29 (  9.9x) |    50 ( 17.1x) |    50 ( 17.1x)
 drones   100 steel_mills  1000 |    14 ( 240.0x) |     0 (  0.0x) |     0 (  0.0x) |     1 ( 17.1x) |     2 ( 34.3x)
 drones  1000 steel_mills  1000 |   140 ( 240.0x) |     2 (  3.4x) |     5 (  8.6x) |    11 ( 18.9x) |    29 ( 49.7x)
 drones  5000 steel_mills  1000 |   700 ( 240.0x) |    14 (  4.8x) |    29 (  9.9x) |    58 ( 19.9x) |   145 ( 49.7x)
 drones   100       silos   200 |     9 (9000.0x) |     0 (  0.0x) |     0 (  0.0x) |     0 (  0.0x) |     0 (  0.0x)
 drones  1000       silos   200 |    93 (9300.0x) |     0 (  0.0x) |     0 (  0.0x) |     0 (  0.0x) |     0 (  0.0x)
 drones  5000       silos   200 |   200 (4000.0x) |     0 (  0.0x) |     0 (  0.0x) |     1 ( 20.0x) |     2 ( 40.0x)
 drones   100       silos  1000 |     9 (9000.0x) |     0 (  0.0x) |     0 (  0.0x) |     0 (  0.0x) |     0 (  0.0x)
 drones  1000       silos  1000 |    93 (9300.0x) |     0 (  0.0x) |     0 (  0.0x) |     0 (  0.0x) |     0 (  0.0x)
 drones  5000       silos  1000 |   466 (9320.0x) |     0 (  0.0x) |     0 (  0.0x) |     1 ( 20.0x) |     2 ( 40.0x)
 cruise    20       farms   200 |    26 (   7.8x) |    16 (  4.8x) |    26 (  7.8x) |    26 (  7.8x) |    26 (  7.8x)
 cruise   100       farms   200 |   133 (   8.0x) |    50 (  3.0x) |    50 (  3.0x) |    50 (  3.0x) |    50 (  3.0x)
 cruise    20       farms  1000 |    26 (   7.8x) |    16 (  4.8x) |    26 (  7.8x) |    26 (  7.8x) |    26 (  7.8x)
 cruise   100       farms  1000 |   133 (   8.0x) |    83 (  5.0x) |   133 (  8.0x) |   133 (  8.0x) |   133 (  8.0x)
 cruise    20 steel_mills   200 |    16 (  19.2x) |     4 (  4.8x) |     8 (  9.6x) |    16 ( 19.2x) |    16 ( 19.2x)
 cruise   100 steel_mills   200 |    80 (  19.2x) |    20 (  4.8x) |    41 (  9.8x) |    50 ( 12.0x) |    50 ( 12.0x)
 cruise    20 steel_mills  1000 |    16 (  19.2x) |     4 (  4.8x) |     8 (  9.6x) |    16 ( 19.2x) |    16 ( 19.2x)
 cruise   100 steel_mills  1000 |    80 (  19.2x) |    20 (  4.8x) |    41 (  9.8x) |    80 ( 19.2x) |    80 ( 19.2x)
 cruise    20       silos   200 |    10 ( 700.0x) |     0 (  0.0x) |     0 (  0.0x) |     0 (  0.0x) |     0 (  0.0x)
 cruise   100       silos   200 |    53 ( 742.0x) |     0 (  0.0x) |     0 (  0.0x) |     1 ( 14.0x) |     3 ( 42.0x)
 cruise    20       silos  1000 |    10 ( 700.0x) |     0 (  0.0x) |     0 (  0.0x) |     0 (  0.0x) |     0 (  0.0x)
 cruise   100       silos  1000 |    53 ( 742.0x) |     0 (  0.0x) |     0 (  0.0x) |     1 ( 14.0x) |     3 ( 42.0x)

Worst case today: rebuild gold destroyed per gold of units, by weapon and
building (stock large enough that nothing runs out; same for any unit count):
   drones at farms             99.9x
   drones at steel_mills      240.0x
   drones at silos           9300.0x
   cruise at farms              8.0x
   cruise at steel_mills       19.2x
   cruise at silos            742.0x

Three strikes in a row (AP allows 3 in a burst), share of the stock destroyed:
  per-strike cap only (round 1): 1 - 0.75^3 = 57.8% (1000 farms: 250, 188, 141 = 579)
  with window + value cap: drones x5000 at 1000 farms: [233, 17, 0] = 25.0%
  with window + value cap: cruise x100 at 1000 steel_mills: [80, 80, 80] = 24.0%
  with window + value cap: drones x5000 at 1000 silos: [1, 1, 1] = 0.3%
```

Reading it:
* K=5 and K=10 also cut cruise missiles at steel mills (19.2x to 9.8x and 4.8x), a pricier weapon that is not the outlier.
* K=20 sits just above cruise at steel mills (19.2x) and cruise at farms (8x): those stay as they are. Drones at farms drop from about 100x to about 20x, drones at steel mills from 240x to about 19x, silos from thousands of x to at most 20x (1,000 drones destroy no silo; 100 cruise missiles destroy 1 instead of 53).
* K=50 leaves drones at farms and steel mills near 50x, so it only closes the silo outlier.
* The share, silo share and window do the rest when the value cap is large (for example 5,000 drones at 200 farms: 50, not 200).

## 4. Constants (all in `wars/strike_building_cap.py`)
`STRIKE_BUILDING_MAX_SHARE = 0.25`, `STRIKE_SILO_MAX_SHARE = 0.10`, `STRIKE_BUILDING_MIN_PER_STRIKE = 1`, `STRIKE_WINDOW_HOURS = 72`, `STRIKE_VALUE_CAP_MULTIPLE = 20`.

## 5. Decisions that are Dede's
1. K (default 20, the least invasive number that closes the drone outliers without touching cruise missiles at farms or steel mills). K=50 is less invasive and leaves drones at about 50x on farms and steel mills.
2. The 25% share and the 10% silo share.
3. The 72h window length.
4. Value counts rebuild gold only (without resources, without policy discount); including resources would raise every ratio.
5. Whether to add a recovery shield or rebuild discount (N3); not built.
6. `record_building_loss` is still called without a province id, so these losses cannot be shown per province.

## 6. Exploit check (docs/templates/EXPLOIT_CHECKLIST.md)
* Timing, new account: Pass. A target with none of the building is refused before anything is spent (existing `_target_has_building`); a first strike on a stock of 1 to 3 destroys 1 if the value cap allows (tested).
* Buy/sell/refund loops: Pass. Nothing is bought or refunded; units are consumed as before. The value cap uses the activation price, so activating more units raises the allowance only in proportion to the gold spent.
* Splitting stock over provinces to dodge the share cap: Pass. The caps use the nation-wide total (tested with 4 provinces).
* Repeated strikes: Closed for the share: three strikes in a row destroy at most the share in the window (5,000 drones at 1,000 farms: 233, 17, 0 = 25%, was 57.8% with a per-strike cap only). The value cap stays per strike, so repeated strikes remain bounded by K times the gold actually spent, not by a free allowance.
* Window dodge by hitting a different building type: Open and intended: caps are per type. Several types can still be hit, each within its own limits.
* Window undercount if the log insert fails: Open, small (see section 2).
* Rebuild then strike again: Possible. The window counts losses against the stock at the start of the window, so rebuilding raises the stock and the allowance only by the share of the rebuilt amount.
* Abuse pushed to drones: This change applies to drones and cruise missiles alike. The strategic airstrike keeps its own limits (B11).
* Alts, self-targeting, hidden nations: Unchanged (same route checks). Several attackers hitting one victim share the victim's window, which is stricter than per attacker (intended).
* Ledger: N/A. No gold or resource change (the existing gasoline spend still goes through `ledger.spend_resources`).
* Inputs: Pass. Zero and negative damage, zero stock, unknown prices and huge counts are handled and tested over random inputs.
* Double submit, races: Unchanged (same per-attacker advisory lock). The window read happens under the attacker's lock only, so two different attackers striking the same victim in the same instant can both see the same window total (small race, not closed).
* Visibility: The strike report is unchanged ("destroyed N farms"); the attacker is not told which cap applied (UI not changed here).

## 7. Rollback
Turn the flag off at /admin/flags. Trigger: drone and cruise missile strikes stop being worth their cost against normal-sized targets, or a strike errors. Nothing owned is removed. The added index can stay.
