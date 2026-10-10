# AnO game rules & invariants

**Read this before changing game logic.** It says what each mechanic is supposed
to do, which module is the single source of truth for it, and the rules that must
hold. **Where** things are (every table's writers, every route, every scheduled
job) is generated from the code in [`SYSTEM_MAP.md`](SYSTEM_MAP.md).

Rules marked 🔒 are enforced by a test; the test name is given. If you change a
mechanic, update its section here in the same PR.

---

## 1. The hour (UTC)

| minute | tick | what it does | gate |
|---|---|---|---|
| :00 | `tax_income` | gold from population (age-weighted), consumer-goods bonus | once per hour |
| :00, :10, … | `global_tick` | resource consumption; **military upkeep** and **war supply regen** once per hour inside it | upkeep/supply once per hour |
| :13 | `market_auto_orders` | players' standing market orders | ⚠ ungated |
| :15 | `natural_disasters` | random disasters | once per hour |
| :25 | `generate_province_revenue` | building production **and building upkeep**, pollution/happiness | once per hour |
| :35 | `produce_unit_stockpiles` | unit production | once per hour |
| :40 | `loan_interest` | loan interest garnish | once per hour |
| :45 | `population_growth` | growth, aging, education graduation | once per hour |
| 00:00 | `war_reparation_tax` | truce reparations (see §4) | once per day |
| :05 every 4h | `manpower_increase` | manpower growth | once per hour |
| 04:50 | `bond_tick` | bond interest / maturity | once per day |

- **Once per period** = `task_runs.last_period`, claimed *before* work and committed
  immediately (`app_core/game_ticks/common.py::claim_tick_period`). A tick can never
  bill/pay an hour twice; a tick that crashes before working loses that hour (the
  economy watchdog shows it). 🔒 `tests/test_tick_periods.py`
- **Replaying a lost hour**: only if it truly never ran — set that task's
  `last_period` below the hour, then run the task. Clearing `last_run` does nothing now.
- Taxes land at :00, upkeep is charged at :25: projections must count the tax that
  lands before the next upkeep (`app_core/economy/tick_order.py`).
- 🔒 Each tick pays once, reruns are no-ops, concurrent runs pay once:
  `tests/test_tax_income_tick_real.py`, `tests/test_generate_revenue_tick_real.py`.

## 2. Economy

**One formula, two consumers.** The hourly tick and the page that *shows* the
number must call the same function. Copies drift (fabricated tax multipliers
09-15, 10x land price 09-29). Shared modules today:

| mechanic | single source of truth | used by |
|---|---|---|
| consumer goods distribution + tax bonus | `app_core/economy/consumer_goods.py` | tax tick, revenue page, province card |
| building stat effects (pollution/happiness/productivity) | `app_core/economy/province_effects.py` | revenue tick, province breakdown |
| education graduation (capacity: primary 1000, high school 900, university 5000 per building) | `app_core/game_ticks/population.py::calc_education_graduation` | population tick, province page |
| building purchase cost | `app_core/economy/building_costs.py`, `building_purchase.py` (from `variables.PROVINCE_UNIT_PRICES`) | buy route, all cost displays |
| trade fee (5%, 2% inside a currency union; removed from the economy) | `app_core/market/fees.py` | market, trades, Max button |
| influence (war ranges, nukes) | `influence_formula.py` | find targets, rankings, nukes |

Still duplicated (Phase 4 targets): the province-card tax estimate in
`templates/provinces_v2.html` mirrors `calc_ti`; military upkeep shown in
`countries.py` mirrors `game_ticks/maintenance.py`.

Rules:
- **Consumer goods only reach people through retail buildings in their province**
  (food banks, gas stations, general stores, malls, distribution centers); remote
  delivery counts at `REMOTE_CG_EFFICIENCY`. No retail → CG stay in stock, no bonus.
  🔒 `tests/test_calc_ti_real.py`
- **Gold/resources move through `app_core/market/services.py::give_resource`**: refuses
  negative amounts and overdrafts atomically. 🔒 `tests/test_resources_flow.py`
  (Many older paths still write `stats.gold` / `user_economy` directly — see
  SYSTEM_MAP §2; Phase 3 will route them through one primitive.)
- **Sell offers escrow the goods when posted**; accepting takes them from the bank,
  not the seller. Exception: direct trades **4 and 5** predate escrow and are still
  pending in production (`LEGACY_UNESCROWED_SELL_TRADE_IDS` in
  `app_core/market/routes.py`). 🔒 `tests/test_direct_trade_audit.py`
- Double-spend races are closed with row locks / conditional updates / advisory
  locks; every money action that can be double-clicked has a race test
  (`tests/test_*_no_double_*.py`, `*_no_replay.py`).

## 3. Population

- Growth toward a **nation-wide** comfort level (`nation_comfort`), not per province.
- Losing a battle freezes growth for `LOSS_FREEZE_HOURS`; a nuke for
  `NUKE_FREEZE_HOURS` (`wars/aftermath.py`, table `population_growth_freezes`).
- The age split (`pop_children/working/elderly`) is rescaled by the DB trigger
  `trg_sync_province_population` when only `population` changes. **Never set both**
  `population` and the age columns in one UPDATE — the trigger then recomputes
  population from the ages.

## 4. War

- **Supply**: attacker *and* defender pay unit supply from their own pool; a
  defender can only field what its supply covers (`wars/supply.py`).
- **Aftermath**: won ground/bomber attacks kill civilians nation-wide; bombers also
  hit soldiers/tanks (`wars/aftermath.py`).
- **Defense composition**: a declared domain (ground/naval/air) decides who defends;
  otherwise the saved `/defense` choice. Note: `stats.default_defense` defaults to
  soldiers,tanks,artillery for everyone, so the "top 3 owned" fallback in
  `attack_scripts/war_orchestrator.py` effectively never runs — **kept on purpose
  (Dede, 2026-10-06)**.
- **Nukes**: plan → review → launch with a one-time token; launch takes an advisory
  lock and decrements only while `quantity > 0`; blast deaths then 1% nation-wide
  fallout; Iron Domes get one interception roll (`wars/nuclear.py`).
  🔒 `tests/test_nuclear_strike.py` (incl. two concurrent launches, one nuke)
- **Reparations** (`app_core/game_ticks/taxes.py::war_reparation_tax`, daily, for 7
  days after a truce): loser pays **20% of every resource per day**, **5% for Raze
  wars** (the Raze rate never applied until 2026-10-06: the code compared a DB row
  tuple to the string). 🔒 `tests/test_war_reparations.py`

## 5. Accounts & security

- Discord/Google-only accounts store the provider id in `users.hash` (no password).
  Step-up checks use `app_core/auth/passwords.py::confirm_identity`: password if the
  account has one, otherwise the nation name; disabling 2FA needs an authenticator
  code. 🔒 `tests/test_passwordless_accounts.py`
- Destructive account actions (delete, reset, reveal email, disable 2FA) always
  need that step-up; a session alone is never enough (2026-09-05 incident).
- Every request re-validates the session against `users` (deleted / banned /
  `session_epoch`). Tests with fake users use `tests/_session.py::mark_validated`.
- CSRF is global (Flask-WTF). 🔒 `tests/test_csrf_enforced_on_app.py`

## 6. Adding things (checklists)

🔒 `tests/test_catalog_consistency.py` fails until a new unit/resource/building is
wired everywhere below.

**New unit** — migration adding the `unit_dictionary` row (+ `spyinfo` column if it
can be spied); `variables.UNITS` (or the test's `SPECIAL_UNITS` if it has its own
code path); stats/supply in `units.py`; domain in `Military.UNIT_DOMAINS` (or
`NON_DOMAIN_UNITS`); image in `game_ui.UNIT_LEGACY_IMAGES`; buy card on
`templates/military_v2.html`; any launch/use UI.

**New resource** — `resource_dictionary` row + `spyinfo` column (migration);
`variables.RESOURCES`; image in `game_ui.RESOURCE_LEGACY_IMAGES`; nothing may list
resources by hand — iterate `variables.RESOURCES` (the silver 500 on 10-06).

**New building** — `building_dictionary` row (migration); `PROVINCE_UNIT_PRICES`
`<name>_price` (+ `<name>_resource`); effects in `variables` / `province_effects.py`;
workers/education in variables; image in `game_ui.BUILDING_LEGACY_IMAGES` (a real
HQ image, not a stand-in; public-domain/CC sources credited in a comment).

**New migration** — `migrations/YYYYMMDD_HHMM_name.sql`, re-runnable; after it ships,
refresh `db/schema.sql` with `scripts/snapshot_prod_schema.sh`.

**New scheduled job** — add to `CELERY_BEAT_SCHEDULE`; if it moves money/assets,
gate it in `TASK_PERIODS` and either pass `db=db` to `should_skip_task` or wrap the
task in `common.run_once_per_period(name, lock_id, fn)` (unused lock id).

**Any change** — branch → PR → CI (`prod-shaped`) → auto-merge. Regenerate the map:
`python scripts/generate_system_map.py`.
