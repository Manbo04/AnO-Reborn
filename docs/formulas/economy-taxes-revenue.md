# Economy: hourly tax income and building revenue/upkeep

Every entry below was copied from code by line range. If a number here disagrees with the game, the code changed: re-run `tools/verify_formulas.py`.

## Order of operations (hourly economy ticks, UTC)

The beat schedule is the real order. Defaults can be overridden by env vars (`TAX_INCOME_CRON`, `PROV_REV_CRON`, ...), so the minute values are defaults only.

**Exact rule** (verbatim) - **Source:** `app_core/celery_schedule.py:56-70`
```python
TASK_PERIODS = {
    "tax_income": "hour",
    "generate_province_revenue": "hour",
    "population_growth": "hour",
    "produce_unit_stockpiles": "hour",
    "military_maintenance": "hour",
    "war_supply_regen": "hour",
    "natural_disasters": "hour",
    "loan_interest": "hour",
    "bond_tick": "day",
    # Value-moving jobs gated via common.run_once_per_period():
    "war_reparation_tax": "day",
    "manpower_increase": "hour",  # scheduled every 4h; hour gate stops duplicates
    "war_auto_expiry": "hour",
}
```
**Exact rule** (verbatim) - **Source:** `app_core/celery_schedule.py:82-101`
```python
    "tax_income": {
        "task": "tasks.task_tax_income",
        "schedule": get_crontab_env("TAX_INCOME_CRON", crontab(minute="0")),
    },
    "generate_province_revenue": {
        "task": "tasks.task_generate_province_revenue",
        "schedule": get_crontab_env("PROV_REV_CRON", crontab(minute="25")),
    },
    "produce_unit_stockpiles": {
        "task": "tasks.task_produce_unit_stockpiles",
        "schedule": get_crontab_env("UNIT_PRODUCTION_CRON", crontab(minute="35")),
    },
    "population_growth": {
        "task": "tasks.task_population_growth",
        "schedule": get_crontab_env("POP_GROWTH_CRON", crontab(minute="45")),
    },
    "natural_disasters": {
        "task": "tasks.task_natural_disasters",
        "schedule": get_crontab_env("NATURAL_DISASTERS_CRON", crontab(minute="15")),
    },
```
1. :00 `tax_income` (app_core/celery_schedule.py:84) pays taxes. Gate: once per hour (TASK_PERIODS at app_core/celery_schedule.py:57).
2. :15 `natural_disasters` (app_core/celery_schedule.py:100).
3. :25 `generate_province_revenue` charges building upkeep, produces/consumes resources, applies province effects (app_core/celery_schedule.py:88).
4. :35 `produce_unit_stockpiles` (drones/missiles; see military-units.md) (app_core/celery_schedule.py:92).
5. :40 `loan_interest` (app_core/celery_schedule.py:104).
6. :45 `population_growth` (app_core/celery_schedule.py:96).
7. :50 `war_auto_expiry` (app_core/celery_schedule.py:75).
8. Every 10 min `global_tick` (military maintenance etc., hourly-gated inside) (app_core/celery_schedule.py:143).

Sequence inside the tax tick (app_core/game_ticks/taxes.py): load stats/CG/rations/policies/provinces (taxes.py:224-330) -> effective rations (taxes.py:464-469) -> `compute_tax_income` (taxes.py:473) -> coalition tax on net profit (taxes.py:487-509) -> credit gold (taxes.py:526-527) -> deposit coalition bank (taxes.py:529-547) -> take consumer goods (taxes.py:570-583).

Sequence inside `compute_tax_income` (app_core/economy/tax_formula.py): per-province base (line 66) -> per-province CG need (67) -> CG allocation and CG multiplier (71-75) -> food multiplier (88-89) -> directive multiplier (91) -> `floor` (94).

## Tax income

### Base tax rate per person
**What it is:** the gold each taxed person yields per hour before multipliers.
**Exact rule** (verbatim) - **Source:** `variables.py:4`
```python
DEFAULT_TAX_INCOME = 0.75
```
**Units/range:** gold per taxed person per hour.
**Used by (grep):** `DEFAULT_TAX_INCOME` -> `templates/provinces_v2.html:201`, `app_core/economy/tax_formula.py:27`
**Notes:** `multiplier = base + (base * land_multiplier)` (see next entry).

### Land tax multiplier (per province)
**What it is:** extra tax per acre of land in a province, capped at +100%.
**Exact rule** (verbatim) - **Source:** `variables.py:12`
```python
DEFAULT_LAND_TAX_MULTIPLIER = 0.02  # Multiplier of tax income per land slot
```
**Exact rule** (verbatim) - **Source:** `app_core/economy/tax_formula.py:24-28`
```python
def province_tax_base(population, land, pc, pw, pe, demographic):
    """Pre-multiplier tax income of one province."""
    land_multiplier = min((land - 1) * variables.DEFAULT_LAND_TAX_MULTIPLIER, 1)
    base = variables.DEFAULT_TAX_INCOME
    multiplier = base + (base * land_multiplier)
```
**Units/range:** `land_multiplier` is in 0..1 (cap via `min(..., 1)`); with 0.02 per land that reaches 1 at land = 51.
**Used by (grep):** `DEFAULT_LAND_TAX_MULTIPLIER` -> `templates/provinces_v2.html:201`, `app_core/economy/province_effects.py:213`, `app_core/economy/tax_formula.py:26`
**Notes:** `land - 1` is used, so 1 land gives multiplier 0. Land below 1 would give a negative land_multiplier (no lower clamp in this function).

Computed example (script output, not hand math):
```
land=1, 1000 working people, demographic=True -> 750.0
land=2, 1000 working people, demographic=True -> 765.0
land=26, 1000 working people, demographic=True -> 1125.0
land=51, 1000 working people, demographic=True -> 1500.0
land=100, 1000 working people, demographic=True -> 1500.0
1000 elderly only, land=1 -> 337.5
```

### Taxable population by age bracket
**What it is:** working-age people pay full tax, children none, elderly 45%.
**Exact rule** (verbatim) - **Source:** `variables.py:151-157`
```python
# Tax contribution by age bracket. Children are dependents (no income tax);
# elderly pay a reduced rate; working-age pays full rate.
DEMO_TAX_MULTIPLIER = {
    "pop_working": 1.0,
    "pop_children": 0.0,
    "pop_elderly": 0.45,
}
```
**Exact rule** (verbatim) - **Source:** `app_core/economy/tax_formula.py:29-37`
```python
    if variables.FEATURE_DEMOGRAPHIC_TAX and demographic:
        taxable = (
            (pw or 0) * variables.DEMO_TAX_MULTIPLIER["pop_working"]
            + (pc or 0) * variables.DEMO_TAX_MULTIPLIER["pop_children"]
            + (pe or 0) * variables.DEMO_TAX_MULTIPLIER["pop_elderly"]
        )
    else:
        taxable = population
    return multiplier * taxable
```
**Units/range:** fraction of base rate per person.
**Used by (grep):** `DEMO_TAX_MULTIPLIER` -> `templates/provinces_v2.html:204`, `app_core/economy/tax_formula.py:31`, `app_core/economy/tax_formula.py:32`, `app_core/economy/tax_formula.py:33`; `FEATURE_DEMOGRAPHIC_TAX` -> `app_core/economy/tax_formula.py:29`
**Notes:** If any province has a NULL age-bracket column, `has_demographic_data` is False for the whole nation (tax_formula.py:19-21) and the full `population` is taxed instead.

### Consumer goods (CG) tax multiplier
**What it is:** a province whose CG need is covered pays up to +50% tax.
**Exact rule** (verbatim) - **Source:** `variables.py:5`
```python
CONSUMER_GOODS_TAX_MULTIPLIER = 1.5
```
**Exact rule** (verbatim) - **Source:** `app_core/economy/consumer_goods.py:124-127`
```python
def cg_tax_multiplier(coverage: float) -> float:
    """Tax multiplier for a province given its CG coverage (1.0 .. 1.5)."""
    bonus = variables.CONSUMER_GOODS_TAX_MULTIPLIER - 1.0
    return 1.0 + bonus * max(0.0, min(1.0, coverage))
```
**Exact rule** (verbatim) - **Source:** `app_core/economy/tax_formula.py:71-75`
```python
    if variables.FEATURE_DEMOGRAPHIC_CONSUMPTION:
        alloc = allocate_consumer_goods(needs, cg_caps, consumer_goods)
        income = sum(inc * cg_tax_multiplier(cov) for inc, cov in zip(incomes, alloc["coverage"]))
        removed = alloc["consumed"]
        delivered = sum(alloc["local"]) + sum(alloc["remote"])
```
**Units/range:** multiplier 1.0 (no coverage) to 1.5 (full coverage); coverage clamped 0..1.
**Used by (grep):** `CONSUMER_GOODS_TAX_MULTIPLIER` -> `app_core/economy/consumer_goods.py:126`, `app_core/economy/tax_formula.py:82`; `cg_tax_multiplier` -> `static/tutorial.js:339`, `app_core/economy/consumer_goods.py:124`, `app_core/economy/tax_formula.py:14`, `app_core/economy/tax_formula.py:73`
**Notes:** only when `FEATURE_DEMOGRAPHIC_CONSUMPTION` is True (variables.py:188). The else-branch at tax_formula.py:76-86 is the legacy nation-wide formula (dead while that flag is True).

### Consumer goods demand per province
**What it is:** how many consumer goods a province's people want per hour.
**Exact rule** (verbatim) - **Source:** `variables.py:145-149`
```python
DEMO_CONSUMER_GOODS_CONSUMPTION = {
    "pop_working": 1.0 / 80000,  # ~0.0000125 CG per working person per tick
    "pop_children": 1.2 / 80000,  # higher for children
    "pop_elderly": 2.0 / 80000,  # 2x for elderly (healthcare, comfort)
}
```
**Exact rule** (verbatim) - **Source:** `app_core/economy/consumer_goods.py:62-74`
```python
    if variables.FEATURE_DEMOGRAPHIC_CONSUMPTION and has_demographic_data:
        elderly_mult = (
            variables.POLICY_HEALTHCARE_ELDERLY_CG_MULTIPLIER
            if universal_healthcare
            else 1.0
        )
        rates = variables.DEMO_CONSUMER_GOODS_CONSUMPTION
        return (
            (pop_working or 0) * rates["pop_working"]
            + (pop_children or 0) * rates["pop_children"]
            + (pop_elderly or 0) * rates["pop_elderly"] * elderly_mult
        )
    return float(math.ceil((population or 0) / variables.CONSUMER_GOODS_PER))
```
**Units/range:** CG per person per hour: working 1/80000, children 1.2/80000, elderly 2.0/80000 (x1.2 with Universal Healthcare).
**Used by (grep):** `DEMO_CONSUMER_GOODS_CONSUMPTION` -> `app_core/game_ticks/food.py:504`, `app_core/game_ticks/food.py:507`, `app_core/game_ticks/food.py:511`, `app_core/economy/consumer_goods.py:68`; `province_cg_need` -> `province.py:436`, `province.py:457`, `services/country_service.py:437`, `services/country_service.py:460`, `app_core/economy/consumer_goods.py:53`, `app_core/economy/tax_formula.py:15` (+1 more)
**Notes:** fallback when demographics are missing: `ceil(population / CONSUMER_GOODS_PER)` with `CONSUMER_GOODS_PER = 80000` (variables.py:78).

### Consumer goods delivery capacity (retail) and remote efficiency
**What it is:** each province can only serve its people with its own retail buildings; spare capacity ships to short provinces at reduced efficiency.
**Exact rule** (verbatim) - **Source:** `variables.py:169-181`
```python
CONSUMER_GOODS_DISTRIBUTION_PER_BUILDING = {
    "food_banks": 250000,  # 250k
    "distribution_centers": 1500000,  # 1.5M
    "gas_stations": 1000000,  # 1.0M
    "general_stores": 2500000,  # 2.5M
    "malls": 5000000,  # 5.0M
}
CONSUMER_GOODS_DISTRIBUTION_PER_BUILDING_DEFAULT = 1500000
# Consumer goods are distributed per province (app_core/economy/consumer_goods.py).
# Spare retail capacity in one province can supply another province that has
# too little, but those long-distance deliveries only count at this fraction
# (the goods are consumed in full; the rest is lost to transport).
REMOTE_CG_EFFICIENCY = 0.5
```
**Exact rule** (verbatim) - **Source:** `app_core/economy/consumer_goods.py:77-82`
```python
def province_cg_capacity(building_qty: Mapping[str, int]) -> float:
    """CG distribution capacity of one province from its building counts."""
    caps = variables.CONSUMER_GOODS_DISTRIBUTION_PER_BUILDING
    return float(
        sum((building_qty.get(name, 0) or 0) * cap for name, cap in caps.items())
    )
```
**Exact rule** (verbatim) - **Source:** `app_core/economy/consumer_goods.py:85-121`
```python
def allocate_consumer_goods(
    needs: Sequence[float], capacities: Sequence[float], stockpile: float
) -> dict:
    """Split a nation's CG stockpile across its provinces.

    Returns ``{"coverage": [...], "consumed": int, "local": [...],
    "remote": [...]}`` where ``coverage[i]`` is the effective share (0..1) of
    province i's demand that was met -- local deliveries count fully, remote
    deliveries count at REMOTE_CG_EFFICIENCY. ``consumed`` is how many CG
    leave the stockpile (remote deliveries are consumed in full).
    """
    n = len(needs)
    local = [min(max(needs[i], 0.0), max(capacities[i], 0.0)) for i in range(n)]
    unmet = [max(needs[i], 0.0) - local[i] for i in range(n)]
    spare = sum(max(capacities[i], 0.0) - local[i] for i in range(n))
    total_unmet = sum(unmet)
    ratio = min(1.0, spare / total_unmet) if total_unmet > 0 else 0.0
    remote = [u * ratio for u in unmet]

    deliverable = sum(local) + sum(remote)
    if deliverable <= 0:
        return {"coverage": [0.0] * n, "consumed": 0, "local": local, "remote": remote}

    stock = max(float(stockpile or 0), 0.0)
    supply = min(1.0, stock / deliverable)
    eff = remote_cg_efficiency()
    coverage = [
        (supply * (local[i] + eff * remote[i]) / needs[i]) if needs[i] > 0 else 0.0
        for i in range(n)
    ]
    consumed = int(deliverable) if supply >= 1.0 else int(stock)
    return {
        "coverage": [min(1.0, c) for c in coverage],
        "consumed": consumed,
        "local": local,
        "remote": remote,
    }
```
**Units/range:** capacity is people-equivalents of CG per hour per building.
**Used by (grep):** `CONSUMER_GOODS_DISTRIBUTION_PER_BUILDING` -> `app_core/game_ticks/food.py:377`, `app_core/economy/consumer_goods.py:29`, `app_core/economy/consumer_goods.py:79`, `app_core/economy/building_costs.py:281`; `REMOTE_CG_EFFICIENCY` -> `province.py:489`, `app_core/economy/consumer_goods.py:7`, `app_core/economy/consumer_goods.py:50`, `app_core/economy/consumer_goods.py:93`; `allocate_consumer_goods` -> `province.py:433`, `province.py:469`, `app_core/economy/consumer_goods.py:85`, `app_core/economy/tax_formula.py:13`, `app_core/economy/tax_formula.py:72`
**Notes:** `CONSUMER_GOODS_DISTRIBUTION_PER_BUILDING_DEFAULT` (variables.py:176) is defined; `province_cg_capacity` ignores it (only listed buildings count). Remote deliveries count at `REMOTE_CG_EFFICIENCY` but are consumed in full. Stock shortage scales everything by `supply = min(1, stock/deliverable)` (consumer_goods.py:109).

### CG grace period (expired)
**What it is:** until a date, remote CG counted at full efficiency.
**Exact rule** (verbatim) - **Source:** `variables.py:185`
```python
PER_PROVINCE_CG_GRACE_UNTIL = "2026-10-04T12:00:00+00:00"
```
**Exact rule** (verbatim) - **Source:** `app_core/economy/consumer_goods.py:33-50`
```python
def grace_period_until(now=None):
    """End of the per-province grace period if it's still running, else None."""
    raw = getattr(variables, "PER_PROVINCE_CG_GRACE_UNTIL", "") or ""
    if not raw:
        return None
    try:
        until = datetime.fromisoformat(raw)
    except ValueError:
        return None
    now = now or datetime.now(timezone.utc)
    return until if now < until else None


def remote_cg_efficiency(now=None):
    """How much shipped (remote) goods count: full during the grace period."""
    if grace_period_until(now) is not None:
        return 1.0
    return variables.REMOTE_CG_EFFICIENCY
```
**Notes:** the date is in the past relative to 2026-11-07, so remote efficiency is currently `REMOTE_CG_EFFICIENCY` (0.5). The date is a literal string; the code compares against `datetime.now(timezone.utc)`.

### Food (rations) tax penalty
**What it is:** a rations shortage cuts tax income, up to -30%.
**Exact rule** (verbatim) - **Source:** `variables.py:9-11`
```python
NO_FOOD_TAX_MULTIPLIER = (
    0.7  # How much the tax income will decrease if there's no food -30%
)
```
**Exact rule** (verbatim) - **Source:** `variables.py:79`
```python
RATIONS_PER = 50000  # 1 Ration per x population (lower = more rations needed)
```
**Exact rule** (verbatim) - **Source:** `app_core/economy/tax_formula.py:40-47`
```python
def food_tax_multiplier(provinces, effective_rations):
    """Rations shortage penalty; small new nations get a grace period."""
    total_population = sum(p[0] for p in provinces)
    needed = max(int(total_population // variables.RATIONS_PER), 1)
    rcp = min(0.0, (effective_rations / needed) - 1.0)
    if len(provinces) <= 1 and sum(p[1] for p in provinces) <= 20:
        return 1.0
    return 1.0 + (rcp * (1.0 - variables.NO_FOOD_TAX_MULTIPLIER))
```
**Units/range:** `rcp` in -1..0; multiplier = 1 + rcp * 0.3, so between 0.7 and 1.0.
**Used by (grep):** `NO_FOOD_TAX_MULTIPLIER` -> `app_core/game_ticks/food.py:214`, `app_core/economy/tax_formula.py:47`; `food_tax_multiplier` -> `app_core/economy/tax_formula.py:40`, `app_core/economy/tax_formula.py:89`
**Notes:** nations with 1 province or fewer AND total land <= 20 are exempt (returns 1.0). `needed = max(int(total_population // RATIONS_PER), 1)`. The rations passed in are `min(stock, distribution capacity)` when `FEATURE_RATIONS_DISTRIBUTION` is True (taxes.py:464-469).

### No-energy tax multiplier
**What it is:** a constant that is defined but not used by the tax formula.
**Exact rule** (verbatim) - **Source:** `variables.py:6-8`
```python
NO_ENERGY_TAX_MULTIPLIER = (
    0.85  # How much the tax income will decrease if there's no energy -15%
)
```
**Used by (grep):** `NO_ENERGY_TAX_MULTIPLIER` -> `app_core/game_ticks/energy.py:125`
**Notes:** UNCLEAR: `NO_ENERGY_TAX_MULTIPLIER` has no reference outside its definition (see the grep line above); the tax formula in app_core/economy/tax_formula.py does not read it.

### Directive tax multiplier
**What it is:** active "directives" can multiply the final tax.
**Exact rule** (verbatim) - **Source:** `app_core/economy/tax_formula.py:91-94`
```python
    income *= tax_multiplier

    return {
        "income": int(math.floor(income)),
```
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/taxes.py:473-480`
```python
                ti = compute_tax_income(
                    [tuple(p[:5]) for p in provinces],
                    consumer_goods,
                    [cg_prov_cap_map.get(p[5], 0.0) for p in provinces],
                    healthcare,
                    effective_rations,
                    tax_multiplier=tax_multiplier_for(directive_map.get(user_id)),
                )
```
**Notes:** the directive values themselves live in app_core/directives (see tutorial-onboarding-misc.md). Result is floored, not rounded.

### Coalition (alliance) tax
**What it is:** a coalition can take a percentage of a member's NET tax income into the coalition bank.
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/taxes.py:487-509`
```python
                # Alliance tax: deduct % from NET profit (gross revenue minus building upkeep)
                # so building operating costs are protected and members do not bleed money.
                tax_deducted = 0
                if user_id in coalition_tax_map:
                    col_id, tax_rate = coalition_tax_map[user_id]
                    upkeep = user_building_upkeep.get(user_id, 0)
                    taxable_profit = max(0, money - upkeep)
                    if taxable_profit > 0 and tax_rate > 0:
                        tax_deducted = int(taxable_profit * tax_rate / 100)
                        tax_deducted = min(money, tax_deducted)
                    if tax_deducted > 0:
                        money -= tax_deducted
                        coalition_bank_deposits[col_id] = (
                            coalition_bank_deposits.get(col_id, 0) + tax_deducted
                        )
                        # Logged distinctly (resource='tax', not 'money') so
                        # bankers/tax collectors/leaders can see coalition tax
                        # revenue in the existing bank transaction log instead
                        # of it being indistinguishable from manual deposits
                        # (Kurai's coalition-tax-visibility suggestion).
                        tax_transaction_rows.append(
                            (col_id, user_id, user_id, "tax", tax_deducted, "deposit")
                        )
```
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/taxes.py:435-436`
```python
                        cost_per = variables.NEW_INFRA.get(bname, {}).get("money", 0)
                        user_building_upkeep[uid] = user_building_upkeep.get(uid, 0) + (qty * cost_per)
```
**Units/range:** `tax_rate` is read from `colNames.tax_rate` (a percent, e.g. 5 means 5%); only coalitions with `tax_rate > 0` are loaded (taxes.py:393).
**Notes:** net = gross income minus the sum of `NEW_INFRA[b]["money"] * quantity` over all the member's buildings (base upkeep, without upgrade/policy discounts). `tax_deducted` is capped at `money`.

### Tax tick gate and chunking
**What it is:** how the tick avoids double payment.
**Exact rule** (verbatim) - **Source:** `app_core/celery_schedule.py:23`
```python
    "tax_income": int(os.getenv("TAX_INCOME_MIN_INTERVAL", "3300")),
```
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/taxes.py:195-201`
```python
            chunk_size = int(os.getenv("TAX_INCOME_CHUNK_SIZE", "1000"))
            db.execute(
                "SELECT id FROM users WHERE id > %s ORDER BY id ASC LIMIT %s",
                (last_id, chunk_size),
            )
            users = db.fetchall()
            all_user_ids = [u[0] for u in users]
```
**Notes:** `TAX_INCOME_CHUNK_SIZE` env var, default 1000 users per run; cursor in `task_cursors` resets to 0 when the last chunk is short (taxes.py:654-658).

### War reparation tax (daily)
**What it is:** 20% (5% for Raze wars) of each of the loser's resources goes to the winner every day after a morale-break war.
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/taxes.py:714-725`
```python
            # Remove peace records older than one week (604800 seconds)
            if peace_date < (time.time() - 604800):
                db.execute("DELETE FROM wars WHERE id=%s", (war_id,))

            # Daily plunder is only for wars that ended by a morale break (the
            # loser's morale is 0, so the winner is known). Auto-expired wars
            # are white peace (no winner, no reparations) and surrender wars
            # already paid their spoils once (conditional: no further penalty);
            # with both morales above 0 the old code guessed the winner wrong
            # and robbed the side that had just won the surrender.
            elif status == "ended" or (a_morale > 0 and d_morale > 0):
                continue
```
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/taxes.py:762-776`
```python
                for resource in Economy.resources:
                    resource_amount = resource_amounts.get(resource, 0) or 0

                    # This condition lower or doesn't give reparation_tax at all
                    # NOTE: for now it lowers to only 5% (the basic is 20%)
                    if war_type == "Raze":
                        eco.transfer_resources(
                            resource, resource_amount * (1 / 20), winner
                        )
                    else:
                        # transfer 20% of all resource
                        # (TODO: implement if and alliance won how to give it)
                        eco.transfer_resources(
                            resource, resource_amount * (1 / 5), winner
                        )
```
**Used by (grep):** `war_reparation_tax` -> `tasks.py:55`, `tasks.py:157`, `app_core/game_ticks/taxes.py:697`, `app_core/celery_schedule.py:67`, `app_core/celery_schedule.py:110`
**Units/range:** `1 / 5` = 20% of the loser's CURRENT stock of every resource in `Economy.resources`; `1 / 20` = 5% when `war_type == "Raze"`.
**Notes:** truce rows older than 604800 s (7 days) are deleted instead (taxes.py:715-716). Wars with `status == "ended"` or both morales above 0 are skipped (taxes.py:724-725). Scheduled daily at 00:00 (app_core/celery_schedule.py:112). Gold is not part of the loop (see list below).

The resource list the reparation loop iterates (`Economy.resources`):
**Exact rule** (verbatim) - **Source:** `attack_scripts/Nations.py:79-95`
```python
    resources = [
        "rations",
        "oil",
        "coal",
        "uranium",
        "bauxite",
        "iron",
        "lead",
        "copper",
        "lumber",
        "components",
        "steel",
        "consumer_goods",
        "aluminium",
        "gasoline",
        "ammunition",
    ]
```
**Notes:** this list has 15 resources and does NOT include silver, diamonds or bullion, which ARE in `variables.RESOURCES` (variables.py:375-394), and does not include gold. So war reparations and `transfer_resources` never move silver/diamonds/bullion/gold. `transfer_resources` gives the winner only what the loser actually had (attack_scripts/Nations.py:196-198).

## Building upkeep, production and energy (generate_province_revenue)

### Productivity output multiplier
**What it is:** each province's productivity stat scales output of its buildings.
**Exact rule** (verbatim) - **Source:** `variables.py:74`
```python
DEFAULT_PRODUCTIVITY_PRODUCTION_MULTIPLIER = 0.009  # 9%
```
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/revenue.py:703-712`
```python
                        # Apply productivity multiplier: 0.9% per productivity point
                        # At 50% productivity (neutral): 1.0x multiplier
                        # At 100% productivity: 1.45x multiplier (50 * 0.9% = 45%)
                        # At 0% productivity: 0.55x multiplier (-50 * 0.9% = -45%)
                        if productivity is not None:
                            productivity_multiplier = 1 + (
                                (productivity - 50)
                                * variables.DEFAULT_PRODUCTIVITY_PRODUCTION_MULTIPLIER
                            )
                            plus_amount_multiplier *= productivity_multiplier
```
**Units/range:** multiplier = `1 + (productivity - 50) * 0.009`; 0 -> 0.55, 50 -> 1.0, 100 -> 1.45.
**Used by (grep):** `DEFAULT_PRODUCTIVITY_PRODUCTION_MULTIPLIER` -> `countries.py:443`, `app_core/game_ticks/revenue.py:710`, `app_core/economy/province_energy.py:24`, `app_core/economy/industry_bonuses.py:91`

### Building upkeep (gold) and discounts
**What it is:** every building costs gold per hour; some upgrades/policies cut it.
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/revenue.py:699-726`
```python
                        operating_costs = infra[unit]["money"] * unit_amount
                        plus_amount = 0
                        plus_amount_multiplier = 1

                        # Apply productivity multiplier: 0.9% per productivity point
                        # At 50% productivity (neutral): 1.0x multiplier
                        # At 100% productivity: 1.45x multiplier (50 * 0.9% = 45%)
                        # At 0% productivity: 0.55x multiplier (-50 * 0.9% = -45%)
                        if productivity is not None:
                            productivity_multiplier = 1 + (
                                (productivity - 50)
                                * variables.DEFAULT_PRODUCTIVITY_PRODUCTION_MULTIPLIER
                            )
                            plus_amount_multiplier *= productivity_multiplier

                        # CHEAPER MATERIALS
                        if unit_category == "industry" and upgrades.get("cheapermaterials"):
                            operating_costs *= 0.8
                        # ONLINE SHOPPING
                        if unit == "malls" and upgrades.get("onlineshopping"):
                            operating_costs *= 0.7

                        # INDUSTRIAL SUBSIDIES POLICY
                        if (
                            variables.POLICY_INDUSTRIAL_SUBSIDIES in policies
                            and unit in variables.POLICY_SUBSIDIES_AFFECTED_BUILDINGS
                        ):
                            operating_costs *= variables.POLICY_SUBSIDIES_UPKEEP_REDUCTION
```
**Units/range:** base is `NEW_INFRA[unit]["money"]` per building per hour (see buildings-costs.md).
**Used by (grep):** `POLICY_SUBSIDIES_UPKEEP_REDUCTION` -> `countries.py:106`, `countries.py:398`, `app_core/game_ticks/revenue.py:726`; `POLICY_SUBSIDIES_AFFECTED_BUILDINGS` -> `countries.py:104`, `countries.py:396`, `app_core/game_ticks/revenue.py:724`, `app_core/economy/province_effects.py:63`
**Notes:** "cheapermaterials" is applied to category `industry` (variables.INFRA_TYPE_BUILDINGS) buildings only; "onlineshopping" to malls only; Industrial Subsidies policy id is `variables.POLICY_INDUSTRIAL_SUBSIDIES` (3). Multipliers stack multiplicatively. `operating_costs = int(operating_costs)` truncates after all multipliers (revenue.py:734).

### Partial operation (affordable units)
**What it is:** if money, energy or an input resource is short, only the affordable number of buildings of that type in the province run.
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/revenue.py:745-766`
```python
                        affordable_units = unit_amount
                        has_enough_stuff = {"status": True, "issues": []}

                        # Pending state — only committed to gold_deductions,
                        # provinces_data energy, and resource_deltas AFTER
                        # affordable_units is finalized, scaled to that count
                        # (not the full unit_amount). Prior versions applied
                        # upkeep before checking energy/resources, so failed
                        # buildings still drained gold and could bankrupt idle
                        # nations (e.g. when a power grid collapse zeroed energy)
                        # -- still true here, just per-unit instead of per-type.
                        pending_gold_cost = 0
                        pending_energy_delta = 0
                        pending_resource_deltas_local = {}

                        cost_per_unit = operating_costs / unit_amount
                        if cost_per_unit > 0:
                            affordable_units = min(
                                affordable_units, int(current_money // cost_per_unit)
                            )
                            if affordable_units < unit_amount:
                                has_enough_stuff["issues"].append("money")
```
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/revenue.py:774-786`
```python
                        energy_per_unit = 0
                        if unit == "steel_mills" and upgrades.get("electricarcfurnace"):
                            energy_per_unit = 2  # EAF consumes 2 energy per mill
                        elif unit in energy_consumers:
                            energy_per_unit = 1  # Each unit consumes 1 energy

                        if energy_per_unit:
                            prov_data = provinces_data.get(province_id, {})
                            current_energy = prov_data.get("energy", 0)
                            affordable_by_energy = int(current_energy // energy_per_unit)
                            if affordable_by_energy < affordable_units:
                                has_enough_stuff["issues"].append("energy")
                            affordable_units = min(affordable_units, affordable_by_energy)
```
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/revenue.py:830-838`
```python
                            affordable_by_resource = int(
                                effective_current // amount_per_unit
                            )
                            if affordable_by_resource < affordable_units:
                                has_enough_stuff["issues"].append(resource)
                            affordable_units = min(affordable_units, affordable_by_resource)

                        affordable_units = max(0, affordable_units)
                        has_enough_stuff["status"] = affordable_units > 0
```
**Notes:** the limit is the minimum across gold, energy and each input resource. A building type with 0 affordable units is skipped entirely (revenue.py:840-846): no upkeep, no output, no effects. Gold available is `stats.gold` at the start of the chunk minus deductions already queued this run (revenue.py:730-732).

### Energy per building
**What it is:** most processing/retail/public buildings consume electricity from their own province.
**Exact rule** (verbatim) - **Source:** `variables.py:406-429`
```python
ENERGY_CONSUMERS = [
        "distribution_centers",
        "food_banks",
    "gas_stations",
    "general_stores",
    "farmers_markets",
    "malls",
    "banks",
    "workshops",
    "jewelry_stores",
    "automotive_plants",
    "city_parks",
    "hospitals",
    "libraries",
    "universities",
    "monorails",
    "railways",
    "metros",
    "component_factories",
    "steel_mills",
    "ammunition_factories",
    "aluminium_refineries",
    "oil_refineries",
]
```
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/revenue.py:774-778`
```python
                        energy_per_unit = 0
                        if unit == "steel_mills" and upgrades.get("electricarcfurnace"):
                            energy_per_unit = 2  # EAF consumes 2 energy per mill
                        elif unit in energy_consumers:
                            energy_per_unit = 1  # Each unit consumes 1 energy
```
**Units/range:** 1 energy per building per hour, except steel mills with Electric Arc Furnace which use 2.
**Used by (grep):** `ENERGY_CONSUMERS` -> `app_core/game_ticks/energy.py:60`, `app_core/game_ticks/revenue.py:131`, `app_core/economy/province_power.py:23`, `app_core/economy/building_costs.py:382`, `app_core/economy/province_energy.py:85`, `app_core/economy/province_effects.py:116`
**Notes:** a province's `energy` is reset to 0 at the start of each province pass (revenue.py:392-393) and built up by power plants processed earlier in `variables.BUILDINGS` order (power plants are first, variables.py:512-518). Energy is per province, not shared across the nation.

### Input resource cost modifiers
**What it is:** upgrades change how many input resources processing buildings burn.
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/revenue.py:798-818`
```python
                        for resource, base_amount in minus.items():
                            amount_per_unit = base_amount

                            # AUTOMATION INTEGRATION
                            if unit == "component_factories" and upgrades.get(
                                "automationintegration"
                            ):
                                amount_per_unit *= 0.75
                            # LARGER FORGES
                            if unit == "steel_mills" and upgrades.get("largerforges"):
                                amount_per_unit *= 0.7

                            # INTEGRATED STEELMAKING
                            if unit == "steel_mills" and upgrades.get("integratedsteelmaking"):
                                amount_per_unit *= 1.36

                            # ELECTRIC ARC FURNACE
                            if unit == "steel_mills" and upgrades.get("electricarcfurnace"):
                                amount_per_unit *= 0.5

                            per_unit_minus[resource] = amount_per_unit
```
**Units/range:** multipliers: automationintegration x0.75 (component_factories), largerforges x0.7, integratedsteelmaking x1.36, electricarcfurnace x0.5 (steel_mills).
**Notes:** they multiply together for steel mills (0.7 * 1.36 * 0.5 when all owned).

### Output formula
**What it is:** the amount of each produced resource.
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/revenue.py:906-910`
```python
                        plus = dict(infra[unit].get("plus", {}))

                        # BETTER ENGINEERING
                        if unit == "nuclear_reactors" and upgrades.get("betterengineering"):
                            plus["energy"] += 6
```
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/revenue.py:928-933`
```python
                        plus_amount_multiplier += project_output_bonus(unit, upgrades)

                        if unit == "farms":
                            plus_amount += int(
                                land * variables.LAND_FARM_PRODUCTION_ADDITION
                            )
```
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/revenue.py:959-981`
```python
                        plus_amount_multiplier *= bonus["multiplier"]

                        # PHASE 3: Apply workforce efficiency multiplier
                        # (reduces production if understaffed)
                        debuff_info = workforce_debuffs.get(
                            user_id, {"efficiency_multiplier": 1.0}
                        )
                        plus_amount_multiplier *= debuff_info.get(
                            "efficiency_multiplier", 1.0
                        )

                        # Function for _plus
                        for resource, amount in plus.items():
                            # Per-unit flat bonus (farm land bonus) is added
                            # BEFORE scaling by units: land bonus applies to
                            # every farm. Vote pending on the final system.
                            amount += plus_amount
                            amount *= affordable_units
                            amount *= plus_amount_multiplier
                            # Normalize production to integer units so we don't
                            # persist fractional resources (e.g., 0.5 rations).
                            # Use ceil to avoid losing tiny outputs.
                            amount = math.ceil(amount)
```
**Units/range:** `amount = ceil((base_plus + farm_land_bonus) * affordable_units * plus_amount_multiplier)`.
**Used by (grep):** `LAND_FARM_PRODUCTION_ADDITION` -> `countries.py:421`, `province.py:615`, `app_core/game_ticks/revenue.py:932`, `app_core/economy/building_costs.py:357`
**Notes:** `plus_amount_multiplier` = (productivity multiplier + national-project additive bonus) x (1+scale) x (1+integration) x workforce efficiency. The national-project bonus is ADDED to the productivity multiplier (app_core/economy/project_bonuses.py:9-16 docstring; code at revenue.py:928). Farm land bonus = `int(land * 3)` per farm, added before scaling. Nuclear reactors with `betterengineering` get +6 energy (revenue.py:909-910). Always rounded UP (`math.ceil`).

### National project output bonuses
**What it is:** three upgrades add a share of base output.
**Exact rule** (verbatim) - **Source:** `app_core/economy/project_bonuses.py:23-35`
```python
PROJECT_OUTPUT_BONUSES: dict[str, tuple[str, float]] = {
    "bauxite_mines": ("strongerexplosives", 0.45),
    "farms": ("advancedmachinery", 0.5),
    "steel_mills": ("integratedsteelmaking", 0.36),
}


def project_output_bonus(building: str, upgrades: Mapping[str, bool]) -> float:
    """Additive output bonus (share of base output) from national projects."""
    entry = PROJECT_OUTPUT_BONUSES.get(building)
    if entry and upgrades.get(entry[0]):
        return entry[1]
    return 0.0
```
**Used by (grep):** `project_output_bonus` -> `countries.py:17`, `countries.py:450`, `province.py:39`, `province.py:612`, `app_core/game_ticks/revenue.py:67`, `app_core/game_ticks/revenue.py:928` (+3 more); `PROJECT_OUTPUT_BONUSES` -> `app_core/economy/building_costs.py:299`, `app_core/economy/building_costs.py:360`, `app_core/economy/project_bonuses.py:23`, `app_core/economy/project_bonuses.py:32`

### Specialisation (economies of scale) bonus
**What it is:** the larger a province's share of one producing building type, the more each produces, up to +15%.
**Exact rule** (verbatim) - **Source:** `app_core/economy/industry_bonuses.py:34-36`
```python
SCALE_MAX_BONUS = 0.15  # asymptotic cap: +15% output
SCALE_CURVE_K = 4.0  # steepness: 25% of slots -> ~+9.5%, 50% -> ~+13%
INTEGRATION_MAX_BONUS = 0.10  # +10% output when fully self-sufficient
```
**Exact rule** (verbatim) - **Source:** `app_core/economy/industry_bonuses.py:64-69`
```python
def scale_bonus(count_in_province: int, province_slots: int) -> float:
    """Specialisation bonus (0..SCALE_MAX_BONUS) for one building type."""
    if count_in_province <= 0 or province_slots <= 0:
        return 0.0
    share = min(1.0, count_in_province / province_slots)
    return SCALE_MAX_BONUS * (1.0 - math.exp(-SCALE_CURVE_K * share))
```
**Exact rule** (verbatim) - **Source:** `app_core/economy/industry_bonuses.py:153-155`
```python
def province_slots_for(building: str, land: int, city_count: int) -> int:
    """The province slot pool a building type competes for."""
    return int(city_count or 0) if building in CITY_UNITS else int(land or 0)
```
**Units/range:** `bonus = 0.15 * (1 - exp(-4.0 * share))`, share = buildings of the type / slots (city_count for CITY_UNITS buildings, land otherwise), share clamped to 1.
**Used by (grep):** `scale_bonus` -> `app_core/economy/industry_bonuses.py:64`, `app_core/economy/industry_bonuses.py:97`, `app_core/economy/industry_bonuses.py:178`; `production_bonuses` -> `countries.py:14`, `countries.py:454`, `province.py:512`, `province.py:536`, `app_core/game_ticks/revenue.py:61`, `app_core/game_ticks/revenue.py:940` (+1 more)
**Notes:** applies to buildings in `SCALE_BUILDINGS` = industry + processing + industrial_district (industry_bonuses.py:40-44).

Computed example:
```
scale_bonus(0 buildings, 100 slots) = 0.000000
scale_bonus(1 buildings, 100 slots) = 0.005882
scale_bonus(25 buildings, 100 slots) = 0.094818
scale_bonus(50 buildings, 100 slots) = 0.129700
scale_bonus(100 buildings, 100 slots) = 0.147253
```

### Vertical integration bonus
**What it is:** a processing building produces up to +10% more when its own province produces its inputs.
**Exact rule** (verbatim) - **Source:** `app_core/economy/industry_bonuses.py:109-150`
```python
def self_sufficiency(
    building: str,
    local_counts: Mapping[str, int],
    output_multipliers: Mapping[str, float] | None = None,
) -> float:
    """How much of a processing building's inputs its province produces itself.

    For each input, the province's real hourly output of it (producer count x
    base rate x ``output_multipliers``, which default to 1.0 = base rate) is
    compared with what the province's buildings of this type consume. The
    scarcest input sets the ratio (0..1).
    """
    mult = output_multipliers or {}
    minus = _infra(building).get("minus") or {}
    own = local_counts.get(building, 0) or 0
    if not minus or own <= 0:
        return 0.0
    producers = _producers_by_resource()
    ratios = []
    for resource, per_unit in minus.items():
        demand = own * float(per_unit)
        if demand <= 0:
            continue
        supply = sum(
            (local_counts.get(b, 0) or 0) * amount * mult.get(b, 1.0)
            for b, amount in producers.get(resource, ())
        )
        ratios.append(min(1.0, supply / demand))
    return min(ratios) if ratios else 0.0


def integration_bonus(
    building: str,
    local_counts: Mapping[str, int],
    output_multipliers: Mapping[str, float] | None = None,
) -> float:
    """Vertical-integration bonus (0..INTEGRATION_MAX_BONUS)."""
    if building not in PROCESSING_BUILDINGS:
        return 0.0
    return INTEGRATION_MAX_BONUS * self_sufficiency(
        building, local_counts, output_multipliers
    )
```
**Units/range:** 0..0.10; ratio is `min(supply/demand)` over inputs, supply counts province producers at real output multipliers.
**Used by (grep):** `integration_bonus` -> `app_core/economy/industry_bonuses.py:140`, `app_core/economy/industry_bonuses.py:183`; `self_sufficiency` -> `province.py:513`, `province.py:551`, `province.py:553`, `templates/province.html:971`, `templates/province.html:1801`, `templates/province.html:1843` (+24 more)
**Notes:** the combined multiplier is `(1 + scale) * (1 + integration)` (industry_bonuses.py:187).

### Workforce efficiency (jobs vs workers)
**What it is:** if a nation has fewer workers than its buildings need, ALL production is scaled down, floor 20%, never above 100%.
**Exact rule** (verbatim) - **Source:** `variables.py:310-314`
```python
UNEMPLOYMENT_THRESHOLD = 0.3  # 30%+ unemployment triggers debuff
UNEMPLOYMENT_HAPPINESS_PENALTY = 10  # Happiness loss per tick
PENSION_CRISIS_RATIO = 0.4  # Elderly > 40% of working = pension crisis
PENSION_CRISIS_GOLD_PENALTY = 5000  # Gold cost per tick when in crisis
PRODUCTION_EFFICIENCY_MIN = 0.2  # Minimum 20% production if severely understaffed
```
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/revenue.py:502-514`
```python
                        if jobs_needed > 0:
                            employment_ratio = jobs_available / jobs_needed
                            # Clamp: workforce shortage floors at PRODUCTION_EFFICIENCY_MIN;
                            # workforce surplus does NOT boost production above 1.0.
                            efficiency_multiplier = min(
                                1.0,
                                max(
                                    variables.PRODUCTION_EFFICIENCY_MIN,
                                    employment_ratio,
                                ),
                            )
                        else:
                            efficiency_multiplier = 1.0
```
**Exact rule** (verbatim) - **Source:** `app_core/economy/workforce.py:4-15`
```python
def jobs_available(edu_recorded: int, pop_working: int) -> int:
    """Workers that can fill building jobs.

    Education buckets (edu_none/highschool/college) only grow when children
    graduate, so working-age people who never got an education record (new
    provinces, the seeded starter population, population redistributed between
    age groups) are missing from them. They are still workers: the
    unemployment rate already counts them (calc_unemployment_rate, 2026-10-05),
    and efficiency must too, otherwise a growing nation loses production and
    then power and retail output for no visible reason (celess, 2026-10-14).
    """
    return int(max(edu_recorded or 0, pop_working or 0))
```
**Units/range:** `efficiency = min(1.0, max(0.2, jobs_available / jobs_needed))`; `jobs_available = max(sum of edu buckets, pop_working)`.
**Used by (grep):** `PRODUCTION_EFFICIENCY_MIN` -> `countries.py:348`, `app_core/game_ticks/population.py:996`, `app_core/game_ticks/revenue.py:509`, `app_core/economy/province_energy.py:70`; `jobs_available` -> `countries.py:323`, `countries.py:345`, `templates/mechanics.html:442`, `app_core/game_ticks/population.py:902`, `app_core/game_ticks/population.py:913`, `app_core/game_ticks/population.py:943` (+13 more)
**Notes:** jobs_needed = sum over `BUILDING_EMPLOYMENT_MATRICES` of worker_count x nation building count (revenue.py:484-489). Computed per NATION, then applied to every province.

### Unemployment happiness penalty
**What it is:** 30%+ unemployment costs -10 happiness per hour in every province.
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/revenue.py:516-521`
```python
                        happiness_penalty = 0
                        gold_penalty = 0
                        if unemployment_rate > variables.UNEMPLOYMENT_THRESHOLD:
                            happiness_penalty = variables.UNEMPLOYMENT_HAPPINESS_PENALTY
                        if pension_ratio > variables.PENSION_CRISIS_RATIO:
                            gold_penalty = variables.PENSION_CRISIS_GOLD_PENALTY
```
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/revenue.py:1089-1102`
```python
                debuff_info = workforce_debuffs.get(user_id, {"happiness_penalty": 0})
                unemployment_penalty = debuff_info.get("happiness_penalty", 0)
                
                # Apply Widespread Propaganda: completely nullify unemployment happiness penalty
                if upgrades.get("widespreadpropaganda"):
                    unemployment_penalty = 0
                    
                if unemployment_penalty > 0 and province_id in provinces_data:
                    # Reduce happiness by unemployment penalty
                    current_hap = provinces_data[province_id].get("happiness", 50)
                    new_hap = max(0, current_hap - unemployment_penalty)
                    provinces_data[province_id]["happiness"] = new_hap
                    # Track for logging
                    happiness_penalties[province_id] = unemployment_penalty
```
**Units/range:** `unemployment_rate > 0.3` (strictly greater) -> -10 happiness; floored at 0.
**Notes:** the `widespreadpropaganda` upgrade sets the penalty to 0 (revenue.py:1093-1094). Rate comes from `calc_unemployment_rate` (see population.md).

### Pension crisis gold penalty
**What it is:** if elderly exceed 40% of working-age people, the nation pays a flat 5000 gold per hour.
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/revenue.py:498-500`
```python
                        pension_ratio = 0.0
                        if total_pop_working > 0:
                            pension_ratio = total_pop_elderly / total_pop_working
```
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/revenue.py:518-521`
```python
                        if unemployment_rate > variables.UNEMPLOYMENT_THRESHOLD:
                            happiness_penalty = variables.UNEMPLOYMENT_HAPPINESS_PENALTY
                        if pension_ratio > variables.PENSION_CRISIS_RATIO:
                            gold_penalty = variables.PENSION_CRISIS_GOLD_PENALTY
```
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/revenue.py:1145-1181`
```python
                        if province_id in provinces_data:
                            current_hap = provinces_data[province_id].get("happiness", 50)
                            new_hap = max(
                                0,
                                current_hap - variables.POLICY_RATIONING_HAPPINESS_PENALTY,
                            )
                            provinces_data[province_id]["happiness"] = new_hap

            # ============ BATCH WRITE ALL ACCUMULATED CHANGES ============
            # PHASE 3: Apply pension crisis gold penalties
            pension_penalties = {}  # user_id -> penalty_amount
            if variables.FEATURE_PHASE3_WORKFORCE:
                # The pension is a flat per-tick cost, but provinces are processed
                # in chunks and every chunk that contains one of a nation's
                # provinces sees that nation. Bill it only in the chunk holding
                # the nation's lowest province id, otherwise a nation spread over
                # N chunks pays N x per hour (Discord, 2026-11-04: 10K/tick shown
                # instead of 5K).
                chunk_province_ids = {row[0] for row in infra_ids}
                dbdict.execute(
                    "SELECT userId, MIN(id) AS first_id FROM provinces "
                    "WHERE userId = ANY(%s) GROUP BY userId",
                    (all_user_ids,),
                )
                pension_first_province = {
                    row["userid"]: row["first_id"] for row in dbdict.fetchall()
                }
                for user_id, debuff_info in workforce_debuffs.items():
                    gold_penalty = debuff_info.get("gold_penalty", 0)
                    if pension_first_province.get(user_id) not in chunk_province_ids:
                        gold_penalty = 0
                    if gold_penalty > 0:
                        gold_deductions[user_id] = (
                            gold_deductions.get(user_id, 0) + gold_penalty
                        )
                        pension_penalties[user_id] = gold_penalty

```
**Units/range:** `elderly / working > 0.4` (strict).
**Notes:** billed once per nation per run, in the chunk that holds its lowest province id (revenue.py:1163-1175). Logged as part of `building_upkeep` ledger minus pension (revenue.py:1388).

### Natural pollution decay
**What it is:** each hour every province with pollution loses 5% (min 1) plus 1 more in vegetated biomes.
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/revenue.py:1196-1205`
```python
                        # Natural pollution decay (AndyTheHusky suggestion):
                        # Smog naturally dissipates over time. High pollution clears faster,
                        # tapering as air quality clears. Vegetated biomes absorb extra pollution.
                        curr_poll = data.get("pollution", 0)
                        if curr_poll > 0:
                            decay = max(1, int(round(curr_poll * 0.05)))
                            loc = str(data.get("location") or "Grassland").lower()
                            if any(b in loc for b in ("jungle", "boreal", "forest", "grassland")):
                                decay += 1
                            data["pollution"] = max(0, curr_poll - decay)
```
**Units/range:** `decay = max(1, int(round(pollution * 0.05)))`; +1 if the nation biome name (stats.location) contains jungle, boreal, forest or grassland.
**Notes:** pollution accumulates uncapped during the building pass and is clamped 0..100 once when written (app_core/economy/province_effects.py:7-14 docstring; revenue.py:1232).

### Province stat effects of buildings
**What it is:** buildings add/subtract happiness, pollution, productivity.
**Exact rule** (verbatim) - **Source:** `app_core/economy/province_effects.py:36-67`
```python
def building_effects_per_unit(unit, upgrades, policies):
    """Return (eff, effminus) for ONE unit of `unit`, with every upgrade and
    policy modifier the tick applies. Values may be fractional; callers
    multiply by the unit count and then round with effect_total()."""
    infra = variables.NEW_INFRA.get(unit, {})
    eff = dict(infra.get("eff", {}) or {})
    effminus = dict(infra.get("effminus", {}) or {})
    upgrades = upgrades or {}
    policies = policies or []

    if unit == "universities" and 3 in policies:
        eff["productivity"] *= 1.10
        eff["happiness"] *= 1.10

    if unit == "hospitals" and upgrades.get("nationalhealthinstitution"):
        eff["happiness"] = int(eff["happiness"] * 1.3)

    if unit in ("monorails", "railways", "metros") and upgrades.get("highspeedrail"):
        eff["productivity"] = int(eff["productivity"] * 1.2)

    if "pollution" in eff:
        # GOVERNMENT REGULATION: retail pollutes 25% less.
        if unit_category(unit) == "retail" and upgrades.get("governmentregulation"):
            eff["pollution"] *= 0.75
        # INDUSTRIAL SUBSIDIES policy: affected buildings pollute more.
        if (
            variables.POLICY_INDUSTRIAL_SUBSIDIES in policies
            and unit in variables.POLICY_SUBSIDIES_AFFECTED_BUILDINGS
        ):
            eff["pollution"] *= variables.POLICY_SUBSIDIES_POLLUTION_MULTIPLIER

    return eff, effminus
```
**Exact rule** (verbatim) - **Source:** `app_core/economy/province_effects.py:75-87`
```python
def apply_effect(current, eff_name, amount, sign, percentage_based):
    """Apply one building type's effect to a province stat.

    Pollution (DEFERRED_CLAMP_STATS) is left unclamped here so reductions
    act on the real, uncapped total; the caller clamps it once at the end
    with clamp_percentage(). Other percentage stats keep their existing
    per-step clamp."""
    new_value = current + amount if sign == "+" else current - amount
    if eff_name in DEFERRED_CLAMP_STATS:
        return new_value
    if eff_name in percentage_based:
        return clamp_percentage(new_value)
    return max(0, new_value)
```
**Notes:** policy ids in this function are hardcoded integers. `3 in policies` on universities gives x1.10 productivity and happiness (province_effects.py:46-48), while `variables.POLICY_INDUSTRIAL_SUBSIDIES == 3` and the country page text for policy 3 says "Industrial building upkeep -30%, Pollution from industry +30%". CONFLICT: see tech-upgrades-policies.md "Hidden legacy policy effects".

### Policy happiness modifiers (applied after buildings)
**What it is:** happiness bonuses/penalties from national policies each hour.
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/revenue.py:1120-1151`
```python
                # Universal Healthcare: +5 happiness per province
                if variables.POLICY_UNIVERSAL_HEALTHCARE in policies:
                    for province_id in prov_ids:
                        if province_id in provinces_data:
                            current_hap = provinces_data[province_id].get("happiness", 50)
                            new_hap = min(
                                100,
                                current_hap + variables.POLICY_HEALTHCARE_HAPPINESS_BONUS,
                            )
                            provinces_data[province_id]["happiness"] = new_hap

                # Mandatory Schooling: +3 happiness per province
                if variables.POLICY_MANDATORY_SCHOOLING in policies:
                    for province_id in prov_ids:
                        if province_id in provinces_data:
                            current_hap = provinces_data[province_id].get("happiness", 50)
                            new_hap = min(
                                100,
                                current_hap + variables.POLICY_SCHOOLING_HAPPINESS_BONUS,
                            )
                            provinces_data[province_id]["happiness"] = new_hap

                # Rationing Program: -10 happiness per province
                if variables.POLICY_RATIONING_PROGRAM in policies:
                    for province_id in prov_ids:
                        if province_id in provinces_data:
                            current_hap = provinces_data[province_id].get("happiness", 50)
                            new_hap = max(
                                0,
                                current_hap - variables.POLICY_RATIONING_HAPPINESS_PENALTY,
                            )
                            provinces_data[province_id]["happiness"] = new_hap
```
**Units/range:** Healthcare +5 (cap 100), Mandatory Schooling +3 (cap 100), Rationing -10 (floor 0), per province per hour.
**Used by (grep):** `POLICY_HEALTHCARE_HAPPINESS_BONUS` -> `app_core/game_ticks/revenue.py:1127`, `app_core/economy/province_effects.py:158`; `POLICY_SCHOOLING_HAPPINESS_BONUS` -> `app_core/game_ticks/revenue.py:1138`, `app_core/economy/province_effects.py:162`; `POLICY_RATIONING_HAPPINESS_PENALTY` -> `app_core/game_ticks/revenue.py:1149`, `app_core/economy/province_effects.py:166`

### Ordering inside one revenue pass for one province
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/revenue.py:583-587`
```python
                # PHASE 3: Apply population aging using preloaded in-memory data.
                # This avoids per-province query/update churn during hourly revenue tick.
                if variables.FEATURE_PHASE3_WORKFORCE and province_id in provinces_data:
                    try:
                        prov = provinces_data[province_id]
```
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/revenue.py:683-689`
```python
                for unit in columns:
                    unit_amount = units[unit]

                    if unit_amount == 0:
                        continue

                    unit_category = find_unit_category(unit)
```
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/revenue.py:1087-1104`
```python
                # PHASE 3: Track happiness penalty from unemployment debuff
                # (to apply after batch writes)
                debuff_info = workforce_debuffs.get(user_id, {"happiness_penalty": 0})
                unemployment_penalty = debuff_info.get("happiness_penalty", 0)
                
                # Apply Widespread Propaganda: completely nullify unemployment happiness penalty
                if upgrades.get("widespreadpropaganda"):
                    unemployment_penalty = 0
                    
                if unemployment_penalty > 0 and province_id in provinces_data:
                    # Reduce happiness by unemployment penalty
                    current_hap = provinces_data[province_id].get("happiness", 50)
                    new_hap = max(0, current_hap - unemployment_penalty)
                    provinces_data[province_id]["happiness"] = new_hap
                    # Track for logging
                    happiness_penalties[province_id] = unemployment_penalty

                processed += 1
```
1. aging and education graduation (only if `FEATURE_PHASE3_WORKFORCE`) (revenue.py:585-655);
2. each building type in `variables.BUILDINGS` order (revenue.py:683): upkeep/energy/inputs check -> output -> effects;
3. unemployment happiness penalty (revenue.py:1089-1102);
4. policy happiness bonuses for the user's provinces in the chunk (revenue.py:1115-1151);
5. pension penalty (revenue.py:1145-1181); pollution decay, clamp and province write (revenue.py:1196-1260); gold/resources written through `ledger` (revenue.py:1376).

## Not found / open questions
- Where `NO_ENERGY_TAX_MULTIPLIER` is applied (no reference found by grep).
- Whether `countries.get_revenue` (the revenue page projection) matches this tick line for line; only its use of `compute_tax_income` was confirmed (see app_core/economy/tax_formula.py:3-7 docstring, a comment).
