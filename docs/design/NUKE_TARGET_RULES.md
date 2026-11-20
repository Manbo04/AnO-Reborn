# Design: who can nuke whom (class D, flag `nuke_target_rules`, ships OFF)

Decision owner: Dede. Part of the work that lets the `pause_missile_launches` flag end. This branch builds the SAFE rules (range at launch, protection, retaliation exception). The 7 day average score band is DESIGN ONLY (section 4); nothing for it is built.

## 0. Problem and metric
Facts re-verified in code:
* War range is population only: `war_strength = population / 1000`, in range when the target is 75% to 133% of the attacker (`wars/war_range.py`). It is checked when a war is declared; `wars/nuclear.py` `plan_strike` does not check it at launch, so a war declared at equal size stays nukeable after one side shrinks or grows.
* `plan_strike` already blocks on: volley used, no nukes, no provinces, launch influence below `MIN_LAUNCH_INFLUENCE` (1,000,000, not for retaliation).
* Retaliation = the enemy nuked first in this war (`wars.nuclear.is_retaliation`).
* `users.date` is `character varying(10)`, written as `str(datetime.date.today())` at signup (signup.py), so 'YYYY-MM-DD'.
* A Fire All salvo calls `plan_strike` once up front (`execute_salvo`); each warhead then calls it again with `salvo=True`.
Metric: with the flag on, a nuke cannot be launched at a target outside the range, under 100,000 influence or under 14 days old, except as retaliation; with it off nothing changes.

## 1. Rules (flag ON)
Pure function `wars/nuke_eligibility.py` `can_nuke(attacker_strength, target_strength, target_influence, target_age_days, is_retaliation) -> (ok, reason)`:
1. Retaliation: always allowed (skips 2 to 4).
2. Protection by influence: target influence below `NUKE_PROTECTION_MIN_INFLUENCE` (100,000) is refused.
3. Protection by age: account younger than `NUKE_PROTECTION_MIN_AGE_DAYS` (14) is refused. An unreadable or missing date does not protect.
4. Range: `in_war_range(attacker_strength, target_strength)`, reusing `WAR_RANGE_LOW` / `WAR_RANGE_HIGH`, not copied, so a change there applies to nukes as well.
Wiring: `plan_strike` calls it (through `nuke_eligibility.check`, which reads populations, fresh influence and `users.date`) when the flag is on, for single strikes and the up-front salvo gate, after the old checks and before the pause message (the pause message still wins). Warheads inside a salvo (`salvo=True`) are NOT rechecked, because the first warhead kills people and can push the target out of range mid-salvo; the salvo was allowed when it was fired. Auto-retaliation is a retaliation, so it passes. The refusal text is shown by the planner pages through `blocked`, as for the existing reasons.
Not built: a "who can I nuke" list (like Find Targets).

## 2. Numbers
Command: `ENVIRONMENT=DEV python scripts/sim_nuke_target_rules.py` (repo functions only; the influence bound uses population only, real influence is higher):

```
Attacker population 300,000,000 (strength 300,000); target old and rich.
 target pop / attacker pop | OFF (today)  | ON
                       0.5 | not checked | refused: out of range
                      0.74 | not checked | refused: out of range
                      0.75 | not checked | allowed
                       1.0 | not checked | allowed
                      1.33 | not checked | allowed
                      1.34 | not checked | refused: out of range
                       2.0 | not checked | refused: out of range

Protection and retaliation (in range, flag ON):
  influence 99,999                         -> refused
  influence 100,000                        -> allowed
  account 13 days old                      -> refused
  account 14 days old                      -> allowed
  brand new, no influence, RETALIATION     -> allowed

Does the 100,000 influence bar ever bind next to the war range?
A first strike needs 1,000,000 influence (wars/nuclear.py). A target in range holds at least 75% of the attacker's population, so its population-only influence is at least 75% x attacker pop x 0.005.
  attacker pop   min target pop in range   min target influence (pop only)
    10,000,000                 7,500,000                            37,500   <- under the bar
    26,000,000                19,500,000                            97,500   <- under the bar
    27,000,000                20,250,000                           101,250
   100,000,000                75,000,000                           375,000
   300,000,000               225,000,000                         1,125,000
 2,000,000,000             1,500,000,000                         7,500,000
The bar can only bind for an attacker below about 26,666,667 people (one that small reaches 1,000,000 influence only through units, buildings and stockpiles).
```

Findings:
* The range rule does the real work. Today the launch is never rechecked.
* The 100,000 influence bar almost never binds next to the 75% range: a target in range of a launcher that has the 1,000,000 influence a first strike needs holds at least 75% of the launcher's population, which is at least about 100,000 influence on population alone unless the launcher is under roughly 26.7M people. Whether any real launcher is that small and unit-heavy is UNVERIFIED (no live data used). The age rule (14 days) can bind, for a new account whose population is close to the launcher's.
* The influence in the protection test is the live number, as in the existing launch gate. The 7 day average (section 4) would replace it later.

## 3. Constants (all in `wars/nuke_eligibility.py`; the range is in `wars/war_range.py`)
`NUKE_PROTECTION_MIN_INFLUENCE = 100_000`, `NUKE_PROTECTION_MIN_AGE_DAYS = 14`.

## 4. DESIGN ONLY: 7 day average score band (not built)
Goal: a nuke needs the target's score between a share of the launcher's and a multiple of it, measured on a 7 day average so it cannot be moved by selling or buying units just before launch (the reason war range became population only, see `wars/war_range.py`).
* Table (migration, no DDL in handlers): `nuke_score_daily(user_id integer NOT NULL, day date NOT NULL, score bigint NOT NULL, PRIMARY KEY (user_id, day))`, index on `day`, rows older than 14 days deleted by the same tick.
* Tick: new `app_core/game_ticks/nuke_score_snapshot.py`, once per UTC day, following the other period-gated ticks (`TASK_PERIODS` with unit "day" and `claim_tick_period` in `app_core/game_ticks/common.py`, advisory lock plus `task_runs` row), one `INSERT ... SELECT` over all nations using `influence_formula.influence_subquery_sql`, registered in `app_core/celery_schedule.py` (`CELERY_BEAT_SCHEDULE`); regenerate `docs/SYSTEM_MAP.md`. ON CONFLICT DO NOTHING so a retry cannot double-write.
* Which score: influence WITHOUT standing units and nukes (population, buildings, stockpiles), so the number cannot be moved by military purchases; plain influence or live influence are the alternatives. This is the question for Dede.
* Average: mean of the last 7 daily rows; a nation with fewer than 7 rows uses what it has; a nation with none (new) is already covered by the 14 day protection.
* Band: `BAND_LOW` x launcher average <= target average <= `BAND_HIGH` x launcher average. The planning notes' examples were 50% and 300%; they are placeholders and not decided. Retaliation skips the band like the other rules.
* Fits into `can_nuke` as two more arguments (`attacker_avg`, `target_avg`); `check` would read the two averages.
* Cold start: until 7 days of rows exist after the tick ships, either skip the band or use the rows that exist; decide with the flag rollout.
* Open risks: the tick must not double-count at the day boundary; a stale table (tick failed) should fail open (no band) and alert, not block every nuke.

## 5. Decisions that are Dede's
1. 100,000 influence and 14 days (suggested defaults, from the planning notes).
2. Whether the launch should keep using live influence for protection until the average exists.
3. The score band: whether to build it, which score (with or without units), and the low/high numbers.
4. Whether warheads inside a salvo should also be rechecked (not done, see section 1).
5. Whether to add the "who can I nuke" list and the player-facing wording of the refusals.

## 6. Exploit check (docs/templates/EXPLOIT_CHECKLIST.md)
* Timing: Pass. Rules are read inside `plan_strike`, which `execute_strike` and `execute_salvo` call after taking the attacker's advisory lock.
* New account, zero values: Pass. A brand new target is protected (age); zero influence is refused; an unreadable date does not protect (so a data problem cannot lock every nuke).
* Range manipulation by buying or selling units: Pass. Range is population only (tested that units do not change `war_strength`). Population can still change a nation's range (for example by losing people in the war), which is the intended recheck; it cannot be bought or sold like units.
* Protection by selling units: Open and small. The influence bar uses live influence, so a defender that dumps units below 100,000 influence becomes immune; with the range rule the bar rarely binds anyway (section 2). The 7 day average would close it.
* Alts, self-targeting: Unchanged (an active war with the target is required, as before).
* Retaliation abuse: Pass by design. Retaliation needs the enemy to have launched at the attacker first in this war (`nuclear_strikes`), which cannot be faked without a real strike.
* Hidden or AI nations: Same code path, same rule.
* Ledger: N/A. No gold or resources.
* Inputs: Pass. Boundary values tested (749/750, 1330/1331, 99,999/100,000, 13/14 days, None).
* Double submit, races: Unchanged.
* Visibility: The refusal says which rule applied and the numbers. The war range message reuses the existing wording.
* Dead time: no timer added.

## 7. Rollback
Turn the flag off at /admin/flags. Trigger: a legitimate launch is refused (for example an in-range target reported as protected or out of range), or nukes become unusable in real wars. Nothing owned is removed.
