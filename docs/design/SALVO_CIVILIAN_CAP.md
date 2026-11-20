# Design: civilian damage cap per Fire All salvo (class D, flag `nuke_salvo_civilian_cap`, ships OFF)

Decision owner: Dede. Agreed in principle: one salvo may kill at most 25% of the target nation's people and destroy at most 25% of its buildings. Dede: single nukes are not the problem, many at once is. Part of the work that lets the `pause_missile_launches` flag end.

## 0. Problem and metric
A Fire All salvo lands one warhead per enemy province and every warhead also adds nation-wide fallout (`wars/aftermath.py` NUKE_FALLOUT_DEATHS x `wars/rules.py` RADIATION_DAMAGE_MULTIPLIER = 0.5% of every province). Against a small or mid nation one click can take most of its people.
Metric: no salvo takes more than `max(25%, damage of its first warhead)` of the nation's people, buildings or cities. A one-warhead salvo is identical with the flag on and off.

## 1. Rule (flag ON)
* Totals (people, buildings, cities) are read once, before the first warhead.
* The first warhead that gets through is applied in full. The cap for each measure is `max(25% of total, that warhead's own damage)`. So a single warhead is never weakened.
* Deaths count blast deaths plus fallout deaths. Blast takes the allowance first, fallout gets what is left (its percentage is lowered to fit).
* Intercepted warheads do nothing and count for nothing (the cap is only touched by warheads that land).
* A warhead the cap cuts to zero is not fired: the launch is rolled back (savepoint), so it stays in the stockpile and costs no influence. A warhead that is only partly cut is fired and spent with reduced damage.
* Applies to Fire All, retaliation salvos and auto-retaliation (all go through `execute_salvo`). The single-warhead route is untouched (one warhead per volley, nothing to cap).
* Measures are independent: when the death cap is full but buildings still have room, the next warhead still destroys buildings (and kills nobody more).

Code: `wars/salvo_cap.py` (pure math + constants + flag), `wars/nuclear.py` (`execute_strike(..., salvo_cap=)`, `_apply_salvo_cap`, `SalvoClamped`), `wars/nuclear_salvo.py` (`execute_salvo`, `read_salvo_cap`). Flag-off code path is the old SQL, unchanged.

## 2. Numbers (before = flag OFF, after = flag ON)
Command: `ENVIRONMENT=DEV python scripts/sim_salvo_cap.py` (repo functions only, no database; model notes at the top of the script). Full salvo = one warhead per province, no Iron Dome. The province shapes are synthetic and labelled; none is a real player's nation. The "large" shape is from a note about one public country page and is unverified.

```
fallout per warhead = 0.5000% of every province; caps 25% people / 25% buildings / 25% cities

FULL SALVO (one warhead per province)
shape                                                                       prov | OFF died% OFF bld% fired |  ON died%  ON bld% fired  kept
new province (repo defaults: starter pop, land 1, cities 1)                    1 |      60.2     50.0     1 |      60.2     50.0     1     0
new province (repo defaults: starter pop, land 1, cities 1)                    5 |      61.0     50.0     5 |      25.0     20.0     3     2
new province (repo defaults: starter pop, land 1, cities 1)                   20 |      63.8     50.0    20 |      25.0     25.0    10    10
new province (repo defaults: starter pop, land 1, cities 1)                   90 |      74.5     50.0    90 |      25.0     25.0    45    45
hypothetical mid (pop 1M, land 100, cities 15)                                 1 |      41.3     47.0     1 |      41.3     47.0     1     0
hypothetical mid (pop 1M, land 100, cities 15)                                 5 |      42.4     47.0     5 |      25.0     24.9     3     2
hypothetical mid (pop 1M, land 100, cities 15)                                20 |      46.6     47.0    20 |      25.0     25.0    11     9
hypothetical mid (pop 1M, land 100, cities 15)                                90 |      62.4     47.0    90 |      25.0     25.0    48    42
large (pop 29.5M, land 3870, cities 310; from a public-page note, unverifi     1 |       5.3      5.7     1 |       5.3      5.7     1     0
large (pop 29.5M, land 3870, cities 310; from a public-page note, unverifi     5 |       7.2      5.7     5 |       7.2      5.7     5     0
large (pop 29.5M, land 3870, cities 310; from a public-page note, unverifi    20 |      13.9      5.7    20 |      13.9      5.7    20     0
large (pop 29.5M, land 3870, cities 310; from a public-page note, unverifi    90 |      39.4      5.7    90 |      25.0      5.7    90     0

ONE WARHEAD (must be identical OFF and ON)
new province (repo defaults: starter pop, land 1, cities 1)                    1 | OFF 60.20% / 50.00%   ON 60.20% / 50.00%   same=True
new province (repo defaults: starter pop, land 1, cities 1)                    5 | OFF 12.44% / 10.00%   ON 12.44% / 10.00%   same=True
new province (repo defaults: starter pop, land 1, cities 1)                   20 | OFF 3.48% / 2.50%   ON 3.48% / 2.50%   same=True
new province (repo defaults: starter pop, land 1, cities 1)                   90 | OFF 1.16% / 0.56%   ON 1.16% / 0.56%   same=True
hypothetical mid (pop 1M, land 100, cities 15)                                 1 | OFF 41.28% / 46.96%   ON 41.28% / 46.96%   same=True
hypothetical mid (pop 1M, land 100, cities 15)                                 5 | OFF 8.66% / 9.39%   ON 8.66% / 9.39%   same=True
hypothetical mid (pop 1M, land 100, cities 15)                                20 | OFF 2.54% / 2.35%   ON 2.54% / 2.35%   same=True
hypothetical mid (pop 1M, land 100, cities 15)                                90 | OFF 0.95% / 0.52%   ON 0.95% / 0.52%   same=True
large (pop 29.5M, land 3870, cities 310; from a public-page note, unverifi     1 | OFF 5.34% / 5.67%   ON 5.34% / 5.67%   same=True
large (pop 29.5M, land 3870, cities 310; from a public-page note, unverifi     5 | OFF 1.47% / 1.13%   ON 1.47% / 1.13%   same=True
large (pop 29.5M, land 3870, cities 310; from a public-page note, unverifi    20 | OFF 0.74% / 0.28%   ON 0.74% / 0.28%   same=True
large (pop 29.5M, land 3870, cities 310; from a public-page note, unverifi    90 | OFF 0.55% / 0.06%   ON 0.55% / 0.06%   same=True
```

## 3. Constants (all in `wars/salvo_cap.py`)
`SALVO_CIVILIAN_CAP_DEATHS = 0.25`, `SALVO_CIVILIAN_CAP_BUILDINGS = 0.25`, `SALVO_CIVILIAN_CAP_CITIES = 0.25`.

## 4. Decisions that are Dede's
1. The three constants (25% people and buildings are agreed; the cities cap is my addition so the building cap cannot be sidestepped by razing cities).
2. Clamped warheads stay in stock (implemented). The alternative is spending them.
3. Cap measured against the pre-salvo total of the whole nation (implemented), not per province.
4. A warhead is only "clamped to zero" when every measure is full; with the death cap full it still destroys the remaining building allowance.
5. Happiness loss of the struck province is not capped.

## 5. Exploit check (docs/templates/EXPLOIT_CHECKLIST.md)
* Timing, tick, truce: Pass. No tick involved; totals are read inside the attacker's advisory-locked transaction.
* New account, zero values: Pass. A nation with 0 people/buildings has cap 0 and still takes the first warhead as it does today; tested with cap math on small totals.
* Buy/sell/refund loops: Pass. Nothing is bought, refunded or created; a clamped warhead is rolled back, not refunded.
* Ledger: N/A. No gold or resources change in this code (nukes and influence are not ledger resources and the salvo already writes them the same way).
* Special weapons supply and morale: Open, unchanged. Not part of this change.
* Alts, self-targeting, allies: Residual risk. The cap is per salvo. Several attackers (one salvo per war per side) can each take their own 25%. The existing 72h per-province repeat halving still applies, and the planned nation-wide recovery shield (N1) is the proper answer. Not solved here.
* Hit and run, instant re-attack: Unchanged (one volley per war).
* Zero, negative, huge inputs: Pass. Pure functions clamp negatives to 0; fallout bisection is bounded (60 steps); tested with random nations.
* Double submit, races: Pass. The same advisory lock and one-time token as before; the new savepoint is inside that transaction.
* Hidden, AI nations: Same code path, same rule.
* Visibility: The salvo JSON result now has `capped` and `clamped`. The Fire All dialog text does not mention the cap yet (UI not changed in this branch).
* Drones: not paused and not affected. This cap does not move damage onto drones (drones cannot kill people beyond the 2% population strike).

## 6. Rollback
Turn the flag off at /admin/flags. Trigger: a salvo errors, or players report that nukes feel useless (a salvo on a nation with as many provinces as the attacker has nukes never reaches the cap). Nothing owned is removed.
