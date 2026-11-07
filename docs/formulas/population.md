# Population (Population 2.0 is the live model)

Hourly tick `population_growth` runs at minute :45 (app_core/celery_schedule.py:96), once per hour (app_core/celery_schedule.py:59).

## Which model is live
**Pop 2.0 start timestamp:** the old "comfort growth curve" model is bypassed for province demographics once `pop2_active()` is True.
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/population2.py:18-19`
```python
POP2_START = datetime.datetime(2026, 10, 12, 18, 0, 0, tzinfo=datetime.timezone.utc)
GRACE_DAYS = 14
```
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/population2.py:48-55`
```python
def pop2_active(now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    return now >= POP2_START


def in_grace_period(now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    return now < POP2_START + datetime.timedelta(days=GRACE_DAYS)
```
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/population.py:641-643`
```python
        pop2_new = None
        if population2.pop2_active():
            pop2_new = {}
```
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/population.py:702-708`
```python
            for province_row in chunk:
                try:
                    if pop2_new is not None and province_row["id"] in pop2_new:
                        n_c, n_w, n_e = pop2_new[province_row["id"]]
                        population_updates.append(
                            (n_c + n_w + n_e, n_c, n_w, n_e, province_row["id"])
                        )
```
Relative to 2026-11-07, `POP2_START` (2026-10-12 18:00 UTC) is in the past, so the Pop 2.0 path writes each province's children/working/elderly. The old path (`calc_population_growth`, population.py:666-690) only runs for provinces NOT in `pop2_new`. The old nation "comfort" number is still computed and still used for distribution efficiency (see food-rations.md) and for the rations ratio that feeds Pop 2.0 births (population.py:630-638, 659).

## Order of operations (population_growth tick)
1. Preload provinces, rations, distribution capacity, storage buffer (population.py:447-577).
2. Rations needed per province, summed per user (population.py:581-591).
3. Distribution bottleneck, actual consumption and spoilage (population.py:601-628).
4. Per-nation rations ratio and (old-model) nation growth (population.py:630-638).
5. Pop 2.0 `simulate_nation` per nation (population.py:640-664).
6. Write province populations in chunks (population.py:698-720).
7. Aging between children/working/elderly is NOT here: it happens in the hourly revenue tick at :25 (see below).

Inside `simulate_nation` (app_core/game_ticks/population2.py:236-271): per province births/deaths/settlers/emigration via `step_province` (249-253) -> starvation (255-257) -> internal migration (260-270).

## Pop 2.0 constants

### Housing: homes per province
**What it is:** the number of homes a province offers.
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/population2.py:21-25`
```python
BASE_HOMES = 2_000_000
HOMES_PER_DISTRICT = 50_000
HOMES_PER_LAND = 30_000
TRANSIT_BONUS = {"railways": 0.01, "metros": 0.02, "monorails": 0.03}
TRANSIT_MAX = 0.30
```
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/population2.py:58-68`
```python
def homes(districts, land, buildings):
    transit = sum(
        TRANSIT_BONUS[k] * int(buildings.get(k, 0) or 0) for k in TRANSIT_BONUS
    )
    transit = min(TRANSIT_MAX, transit)
    base = (
        BASE_HOMES
        + HOMES_PER_DISTRICT * (districts or 0)
        + HOMES_PER_LAND * (land or 0)
    )
    return int(base * (1 + transit))
```
**Units/range:** homes = int((2,000,000 + 50,000 * X + 30,000 * land) * (1 + transit)), transit = min(0.30, 0.01*railways + 0.02*metros + 0.03*monorails).
**Used by (grep):** `homes` -> `flavor_text.py:224`, `flavor_text_3.py:281`, `flavor_text_2.py:283`, `templates/country.html:166`, `templates/mechanics.html:111`, `templates/mechanics.html:112` (+21 more); `BASE_HOMES` -> `app_core/game_ticks/population2.py:64`; `HOMES_PER_DISTRICT` -> `app_core/game_ticks/population2.py:65`, `app_core/population_needs.py:83`, `app_core/population_needs.py:84`; `HOMES_PER_LAND` -> `app_core/game_ticks/population2.py:66`, `app_core/population_needs.py:85`
**Notes:** the parameter named `districts` is called with the province's `citycount` (app_core/game_ticks/population.py:378 `population2.homes(r["citycount"], r["land"], ...)` and population2.py:247 `homes(p.get("citycount"), ...)`), so "per district" means per CITY. Transit buildings are counted per province.

### Housing factor (births slow when full)
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/population2.py:71-78`
```python
def housing_factor(pop, home_count):
    """1 up to 100% full, linear to 0 at 120%."""
    if home_count <= 0:
        return 0.0
    r = pop / home_count
    if r <= 1:
        return 1.0
    return max(0.0, 1 - (r - 1) / (OVERFLOW_LIMIT - 1))
```
**Units/range:** 1.0 up to 100% full; linear to 0 at `OVERFLOW_LIMIT` 1.20 (population2.py:41).

### Happiness factor
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/population2.py:81-82`
```python
def happiness_factor(happiness):
    return 0.5 + max(0.0, min(100.0, float(happiness or 0))) / 100
```
**Units/range:** 0.5 at happiness 0 to 1.5 at happiness 100 (happiness clamped 0..100).

### Births
**What it is:** children born per hour from the working-age population.
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/population2.py:30`
```python
BIRTH_RATE = 0.025
```
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/population2.py:101-106`
```python
def births(working, pop, home_count, happiness, food_ratio, dt=DT):
    food = max(0.0, min(1.0, float(food_ratio or 0)))
    return int(
        working * BIRTH_RATE * housing_factor(pop, home_count)
        * happiness_factor(happiness) * food * dt
    )
```
**Units/range:** `BIRTH_RATE = 0.025` per working person per GAME DAY; `dt = 1/24` (population2.py:45), so per hour = working * 0.025 * housing_factor * happiness_factor * food_ratio / 24, truncated with `int`.
**Notes:** `food_ratio` = rations ratio clamped 0..1 (0 food = 0 births). No education term.

Computed example (script output):
```
homes(10 cities, 20 land, 5 railways,2 metros) = 3379000
births(working=1,000,000 pop=3,000,000 homes=5,000,000 happy=50 food=1.0) = 1041
births(... homes=2,700,000 -> 111% full) = 462
death_rates(0 hospitals, pop 3,000,000, pollution 0, no healthcare) = (0.06, 0.01)
death_rates(3 hospitals, pop 3,000,000, pollution 0, no healthcare) = (0.020000000000000004, 0.002)
death_rates(3 hospitals, pop 3,000,000, pollution 100, healthcare) = (0.0175, 0.00175)
```

### Deaths and hospitals
**What it is:** elderly and child death rates fall with hospital coverage and rise with pollution.
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/population2.py:31-35`
```python
ELDERLY_DEATH = (0.06, 0.02)  # uncovered, fully covered by hospitals
CHILD_DEATH = (0.01, 0.002)
HEALTHCARE_POLICY_MULT = 0.7
POLLUTION_DEATH_MULT = 0.25
HOSPITAL_CAPACITY = 1_000_000
```
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/population2.py:85-98`
```python
def hospital_cover(hospitals, pop):
    if pop <= 0:
        return 1.0
    return min(1.0, hospitals * HOSPITAL_CAPACITY / pop)


def death_rates(hospitals, pop, pollution, universal_healthcare):
    cover = hospital_cover(hospitals, pop)
    mult = 1 + POLLUTION_DEATH_MULT * max(0.0, float(pollution or 0)) / 100
    if universal_healthcare:
        mult *= HEALTHCARE_POLICY_MULT
    elderly = (ELDERLY_DEATH[0] - (ELDERLY_DEATH[0] - ELDERLY_DEATH[1]) * cover) * mult
    child = (CHILD_DEATH[0] - (CHILD_DEATH[0] - CHILD_DEATH[1]) * cover) * mult
    return elderly, child
```
**Units/range:** rates per game day: elderly 0.06 (no hospitals) to 0.02 (full cover), children 0.01 to 0.002; one hospital covers 1,000,000 people. Multiplied by `1 + 0.25 * pollution/100` and by 0.7 with Universal Healthcare.
**Used by (grep):** `hospital_cover` -> `app_core/game_ticks/population2.py:85`, `app_core/game_ticks/population2.py:92`, `app_core/game_ticks/population.py:385`, `app_core/population_needs.py:31`; `death_rates` -> `app_core/game_ticks/population2.py:91`, `app_core/game_ticks/population2.py:130`; `HOSPITAL_CAPACITY` -> `app_core/game_ticks/population2.py:88`, `app_core/population_needs.py:35`
**Notes:** `hospitals` counted per province (population2.py:252). Applied per hour as `int(e * er * dt)` (population2.py:131-132). Working-age people do not die in this function.

### Settlers (immigration into empty homes)
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/population2.py:37-43`
```python
MIGRATION_RATE = 0.05
SETTLER_RATE = 0.10
SETTLER_CAP_BASE = 500_000
SETTLER_CAP_SHARE = 0.001
OVERFLOW_LIMIT = 1.20
EMIGRATION_RATE = 0.02
SETTLER_WORKING_SHARE = 0.7
```
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/population2.py:109-114`
```python
def settlers(pop, home_count, happiness, food_ratio, dt=DT):
    free = max(0, home_count - pop)
    cap = SETTLER_CAP_BASE + SETTLER_CAP_SHARE * pop
    food = max(0.0, min(1.0, float(food_ratio or 0)))
    daily = min(SETTLER_RATE * free, cap) * happiness_factor(happiness) * food
    return int(daily * dt)
```
**Units/range:** per game day `min(0.10 * free_homes, 500,000 + 0.001 * pop) * happiness_factor * food`, hourly = x dt. 70% of settlers arrive as working-age (`SETTLER_WORKING_SHARE`), the rest as children (population2.py:135,138).

### Emigration
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/population2.py:117-119`
```python
def emigrants(pop, home_count, dt=DT):
    over = pop - OVERFLOW_LIMIT * home_count
    return int(max(0, over) * EMIGRATION_RATE * dt)
```
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/population2.py:136-137`
```python
    out = 0 if grace else emigrants(pop, home_count, dt)
    out_w = min(w, out)
```
**Units/range:** 2% per game day of the people above 120% of homes. Disabled while `in_grace_period()` (14 days after POP2_START = until 2026-10-26 18:00 UTC; in the past on 2026-11-07).
**Notes:** the grace flag passed to `step_province` is `grace` = `in_grace_period(now)` (population2.py:243), not the small-nation flag.

### Internal migration
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/population2.py:141-161`
```python
def distribute_migration(provinces, dt=DT):
    """Internal migration inside ONE nation. provinces: list of dicts with
    id, pop, homes. Returns {id: net_change}. Overflow (above 100%) moves
    MIGRATION_RATE/day to provinces with free homes, in proportion to free."""
    out = {p["id"]: 0 for p in provinces}
    free = {p["id"]: max(0, p["homes"] - p["pop"]) for p in provinces}
    total_free = sum(free.values())
    if total_free <= 0:
        return out
    for p in provinces:
        over = p["pop"] - p["homes"]
        if over <= 0:
            continue
        moving = min(int(over * MIGRATION_RATE * dt), total_free)
        if moving <= 0:
            continue
        out[p["id"]] -= moving
        for q in provinces:
            if free[q["id"]]:
                out[q["id"]] += int(moving * free[q["id"]] / total_free)
    return out
```
**Units/range:** over-100%-full provinces send 5% per game day (`MIGRATION_RATE`, /24 per hour) of their excess to provinces with free homes, in proportion to free homes. Within one nation only.

### Starvation
**What it is:** if rations coverage is below 1, a share of the province dies each hour.
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/population2.py:167-176`
```python
STARVATION_PER_TICK = 0.0025  # up to 0.25%/tick at 0 rations coverage (was 1%)
# The distribution fix and Pop 2.0 went live together on 2026-10-12 18:00 UTC and
# cut how many people big nations' distribution buildings reach. Nobody starves
# for one week while players build up distribution.
STARVATION_GRACE_END = variables.DISTRIBUTION_FIX_START + datetime.timedelta(days=7)


def starvation_grace_active(now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    return now < STARVATION_GRACE_END
```
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/population2.py:255-257`
```python
        if not starve_grace and not starvation_grace_active(now) and food_ratio < 1.0:
            sd = int((c + w + e) * (1.0 - max(0.0, food_ratio)) * STARVATION_PER_TICK)
            c, w, e = _scale_down(c, w, e, sd)
```
**Units/range:** `deaths = int(pop * (1 - food_ratio) * 0.0025)` per hour; skipped when `starve_grace` (nation with <=1 province AND <=20 land, population.py:652-654) or `starvation_grace_active()` (before 2026-10-19 18:00 UTC; past).
**Notes:** the same flag is computed again for the old model with a 1% factor (population.py:256), which is dead while Pop 2.0 is active.

## Aging and education (hourly revenue tick, not population tick)

### Aging rates
**What it is:** how people move children -> working -> elderly each hour.
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/population2.py:27-28`
```python
CHILD_DAYS = 18  # child -> working
WORKING_DAYS = 27  # working (18) -> elderly (45)
```
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/revenue.py:595-620`
```python
                        elderly_death_rate = variables.DEMO_AGING_RATES["elderly_death"]
                        if variables.POLICY_UNIVERSAL_HEALTHCARE in policies:
                            elderly_death_rate *= (
                                variables.POLICY_HEALTHCARE_ELDERLY_DEATH_REDUCTION
                            )

                        from app_core.game_ticks import population2 as _p2
                        _pop2 = _p2.pop2_active()
                        if _pop2:
                            # Population 2.0: deaths happen in population_growth()
                            elderly_death_rate = 0
                        elderly_deaths = int(round(pop_elderly * elderly_death_rate))
                        pop_elderly = max(0, pop_elderly - elderly_deaths)

                        working_to_elderly = int(
                            round(
                                pop_working
                                * (
                                    1 / (_p2.WORKING_DAYS * 24)
                                    if _pop2
                                    else variables.DEMO_AGING_RATES["working_to_elderly"]
                                )
                            )
                        )
                        pop_elderly += working_to_elderly
                        pop_working = max(0, pop_working - working_to_elderly)
```
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/revenue.py:629-630`
```python
                            base_rate=(1 / (_p2.CHILD_DAYS * 24)) if _pop2 else None,
                        )
```
**Units/range:** with Pop 2.0 active: working->elderly = round(working / (27*24)) per hour; graduation base rate = 1 / (18*24) of children per hour (x1.5 with Mandatory Schooling); elderly deaths in this block are zeroed (`elderly_death_rate = 0`), deaths happen in the population tick.
**Notes:** the legacy constants `DEMO_AGING_RATES` and `DEMO_BIRTH_RATE` (variables.py:200-226) are only used when Pop 2.0 is NOT active:
**Exact rule** (verbatim) - **Source:** `variables.py:200-226`
```python
DEMO_AGING_RATES = {
    # Halved 2026-09-05 (was 0.002/0.001): near the population cap, growth
    # throttles to POP_GROWTH_DIMINISHING_FLOOR and only feeds the small
    # children bucket, which children_to_working (1%/tick) can't refill fast
    # enough against the old working_to_elderly+elderly_death drain -- working
    # population (the only 100%-taxed bracket) was shrinking ~0.06%/tick even
    # while total population inched up, so nations at/near cap saw tax revenue
    # decay indefinitely. Player-reported (staff-chat 2026-09-04, Lamlor/
    # Mohammed): "population is increasing but revenue is going down."
    "elderly_death": 0.001,  # 0.1% of elderly die per tick
    "working_to_elderly": 0.0005,  # 0.05% move to elderly per tick
    # 1% graduate to working per tick (was 0.5%, then 2% -- at 2% this ran
    # ~25x faster than births could replenish near the pop cap, see
    # POP_GROWTH_DIMINISHING_FLOOR above; halved 2026-09-02).
    "children_to_working": 0.01,
}

# Organic births: children added per working-age person per tick, on top of
# the capacity-driven growth in population.py's calc_population_growth().
# Added 2026-09-05 alongside the DEMO_AGING_RATES halving above -- ties the
# children inflow to the actual working population (a real birth rate)
# instead of purely to spare capacity under maxPop, so the demographic
# pipeline can sustain itself once growth throttles near the cap. Scaled by
# the same diminishing_factor/rations_ratio as capacity growth and hard-capped
# at maxPop in calc_population_growth(), so it never operates outside the
# existing population-cap or starvation logic (no reopened whale-growth risk).
DEMO_BIRTH_RATE = 0.00025
```
**Used by (grep):** `DEMO_AGING_RATES` -> `app_core/game_ticks/population.py:63`, `app_core/game_ticks/revenue.py:595`, `app_core/game_ticks/revenue.py:615`; `DEMO_BIRTH_RATE` -> no non-definition references found by grep

### Education graduation chain
**What it is:** graduating children become uneducated, high-school or college workers depending on school capacity in the province.
**Exact rule** (verbatim) - **Source:** `variables.py:229-233`
```python
# Students graduating per tick-hour a building can carry (weekly vote 10-16:
# larger multiples of 5,000; a high school needs two primary schools feeding it).
PRIMARY_SCHOOL_CAPACITY = 5000
HIGH_SCHOOL_CAPACITY = 10000
UNIVERSITY_CAPACITY = 40000
```
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/population.py:56-106`
```python
def calc_education_graduation(pop_children, policies, primary_buildings, hs_buildings, uni_buildings, now=None, base_rate=None):
    """Computes tier-chained education graduation for a province. Shared between tick and display."""
    from datetime import datetime, timezone
    
    graduation_rate = (
        base_rate
        if base_rate is not None
        else variables.DEMO_AGING_RATES["children_to_working"]
    )
    if variables.POLICY_MANDATORY_SCHOOLING in policies:
        graduation_rate *= variables.POLICY_SCHOOLING_GRADUATION_MULTIPLIER

    can_graduate = min(pop_children, int(round(pop_children * graduation_rate)))
    
    true_primary_capacity = primary_buildings * variables.PRIMARY_SCHOOL_CAPACITY
    hs_capacity = hs_buildings * variables.HIGH_SCHOOL_CAPACITY
    uni_capacity = uni_buildings * variables.UNIVERSITY_CAPACITY
    
    primary_capacity = true_primary_capacity
    grace_until = None
    
    raw_grace = getattr(variables, "EDUCATION_CHAIN_GRACE_UNTIL", "")
    if raw_grace:
        try:
            grace_dt = datetime.fromisoformat(raw_grace)
            now_dt = now or datetime.now(timezone.utc)
            if now_dt < grace_dt:
                grace_until = grace_dt
                primary_capacity = max(primary_capacity, hs_capacity + uni_capacity)
        except ValueError:
            pass

    passed_primary = min(can_graduate, primary_capacity)
    passed_hs = min(passed_primary, hs_capacity)
    passed_uni = min(passed_hs, uni_capacity)

    return {
        "can_graduate": can_graduate,
        "passed_primary": passed_primary,
        "passed_hs": passed_hs,
        "passed_uni": passed_uni,
        "edu_college_new": passed_uni,
        "edu_highschool_new": passed_hs - passed_uni,
        "edu_none_new": can_graduate - passed_hs,
        "primary_capacity": primary_capacity,
        "true_primary_capacity": true_primary_capacity,
        "hs_capacity": hs_capacity,
        "uni_capacity": uni_capacity,
        "grace_until": grace_until

    }
```
**Units/range:** capacity per building per hour: primary 5000, high school 10000, university 40000. `can_graduate = min(children, round(children * rate))`; `passed_primary = min(can_graduate, primary_cap)`, `passed_hs = min(passed_primary, hs_cap)`, `passed_uni = min(passed_hs, uni_cap)`; college = passed_uni, highschool = passed_hs - passed_uni, none = can_graduate - passed_hs.
**Used by (grep):** `calc_education_graduation` -> `province.py:769`, `province.py:773`, `app_core/game_ticks/population.py:56`, `app_core/game_ticks/revenue.py:622`, `app_core/game_ticks/revenue.py:623`; `PRIMARY_SCHOOL_CAPACITY` -> `app_core/game_ticks/population.py:70`, `app_core/main/routes.py:292`; `HIGH_SCHOOL_CAPACITY` -> `app_core/game_ticks/population.py:71`, `app_core/main/routes.py:293`; `UNIVERSITY_CAPACITY` -> `app_core/game_ticks/population.py:72`, `app_core/main/routes.py:294`
**Notes:** `EDUCATION_CHAIN_GRACE_UNTIL` (variables.py:197) was 2026-10-05; it is past, so primary capacity is the true primary capacity. `EDUCATION_GRADUATION_PRIORITY` (variables.py:236-240) has no effect in this function (UNCLEAR if referenced elsewhere; see grep):
**Used by (grep):** `EDUCATION_GRADUATION_PRIORITY` -> no non-definition references found by grep

### Unemployment rate
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/population.py:873-884`
```python
def calc_unemployment_rate(pop_working, workers_on_record):
    """Share of the working-age population that can't be counted as a worker.

    Working-age people with no education record are still workers (uneducated
    ones). Education buckets only grow on graduation, so treating unrecorded
    people as unemployed made most growing nations look >30% jobless and
    pinned their happiness at 3%/8% (2026-10-05)."""
    if pop_working <= 0:
        return 0.0
    workers = max(workers_on_record, pop_working)
    return max(0.0, 1.0 - workers / pop_working)

```
**Units/range:** `1 - max(edu_recorded, pop_working) / pop_working`, clamped >= 0. Because `workers = max(workers_on_record, pop_working)`, this expression is always 0 (see Notes).
**Notes:** CONFLICT/UNCLEAR: the code line `workers = max(workers_on_record, pop_working)` followed by `1.0 - workers / pop_working` can never be positive, so `unemployment_rate > UNEMPLOYMENT_THRESHOLD` (revenue.py:518) is never True through this function. Computed below. The revenue tick calls `calc_unemployment_rate(total_pop_working, jobs_available)` where `jobs_available = max(edu_total, pop_working)` (revenue.py:477-496), so the unemployment happiness penalty cannot trigger in the live tick.

Computed example (script output):
```
pop_working=1000 edu_recorded=0 jobs_available=1000 unemployment=0.0
pop_working=1000 edu_recorded=500 jobs_available=1000 unemployment=0.0
pop_working=1000 edu_recorded=1000 jobs_available=1000 unemployment=0.0
pop_working=1000 edu_recorded=3000 jobs_available=3000 unemployment=0.0
```

## Legacy "comfort" model (still computed)

### Nation comfort population
**What it is:** a saturating-curve target population for a whole nation, used for distribution efficiency, the old growth curve, and tooltips.
**Exact rule** (verbatim) - **Source:** `variables.py:34-38`
```python
NATION_COMFORT_BASE = 5_000_000
CITY_POP_CAP = 600_000_000
CITY_POP_SOFTNESS = 800
LAND_POP_CAP = 250_000_000
LAND_POP_SOFTNESS = 2083
```
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/population.py:109-128`
```python
def nation_comfort(total_cities, total_land, happiness=50, pollution=50):
    """Comfortable population for a whole nation (NOT per province -- see
    variables.NATION_COMFORT_BASE for why). Saturating curve on total
    cities/land, scaled by the nation's population-weighted happiness and
    pollution the same way the old per-province max population was."""
    c = max(0.0, float(total_cities or 0))
    l = max(0.0, float(total_land or 0))
    comfort = (
        variables.NATION_COMFORT_BASE
        + variables.CITY_POP_CAP * (1 - math.exp(-c / variables.CITY_POP_SOFTNESS))
        + variables.LAND_POP_CAP * (1 - math.exp(-l / variables.LAND_POP_SOFTNESS))
    )
    happiness_multiplier = (
        (happiness - 50) * variables.DEFAULT_HAPPINESS_GROWTH_MULTIPLIER / 50
    )
    pollution_multiplier = (
        (pollution - 50) * -variables.DEFAULT_POLLUTION_GROWTH_MULTIPLIER / 50
    )
    comfort = int(comfort * (1 + happiness_multiplier + pollution_multiplier))
    return max(variables.NATION_COMFORT_BASE, comfort)
```
**Units/range:** comfort = int((5,000,000 + 600,000,000*(1-exp(-cities/800)) + 250,000,000*(1-exp(-land/2083))) * (1 + happy_mult + poll_mult)), floor 5,000,000. `happy_mult = (happiness-50)*0.04/50`, `poll_mult = (pollution-50)*-0.02/50`; happiness/pollution are population-weighted across provinces (population.py:239-240).
**Used by (grep):** `nation_comfort` -> `app_core/game_ticks/population.py:109`, `app_core/game_ticks/population.py:241`, `app_core/economy/province_effects.py:186`; `NATION_COMFORT_BASE` -> `app_core/game_ticks/population.py:111`, `app_core/game_ticks/population.py:117`, `app_core/game_ticks/population.py:128`; `CITY_POP_CAP` -> `app_core/game_ticks/population.py:118`, `app_core/economy/province_effects.py:199`; `LAND_POP_CAP` -> `app_core/game_ticks/population.py:119`, `app_core/economy/province_effects.py:200`
**Notes:** cities and land are summed over the whole nation (population.py:232-233).

Computed example (script output):
```
nation_comfort(cities=0, land=0, happiness=50, pollution=50) = 5000000
nation_comfort(cities=10, land=20, happiness=50, pollution=50) = 14842216
nation_comfort(cities=800, land=2083, happiness=50, pollution=50) = 542302475
nation_comfort(cities=2400, land=6249, happiness=50, pollution=50) = 812680991
overcrowding_efficiency(pop=40M, comfort=10M) = 0.5
calc_nation_growth(pop=1M, comfort=10M, rations_ratio=1.0) = 11440
```

### Overcrowding efficiency
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/population.py:131-138`
```python
def overcrowding_efficiency(nation_population, comfort):
    """Share of their normal capacity distribution buildings still serve.
    1.0 up to comfort, then sqrt(comfort / population): 4x over comfort =
    50%, so a huge nation needs far more distribution to stay fed."""
    pop = float(nation_population or 0)
    if comfort <= 0 or pop <= comfort:
        return 1.0
    return math.sqrt(comfort / pop)
```
**Units/range:** 1.0 up to comfort; above comfort `sqrt(comfort / population)`.

### Old nation growth formula (used for rations ratio only while Pop 2.0 is active)
**Exact rule** (verbatim) - **Source:** `variables.py:47-58`
```python
POP_GROWTH_RATE = 0.004
POP_GROWTH_SEED_RATE = 0.00005
POP_GROWTH_DIMINISHING_FLOOR = 0.05
# Catch-up boost (2026-10-06) so new players don't lag behind: the
# rate-on-current-population part of growth is multiplied by
#   1 + BOOST * (1 - population / comfort) * (1 - population / CATCHUP_POP)
# -- up to 3x for a small, mostly-empty nation, fading to 1x at comfort OR at
# CATCHUP_POP people. The size fade matters: big city-heavy nations (e.g.
# Armed Farmers, 190M of ~790M comfort) would otherwise get ~2.5x and undo
# the 2026-10-04 province-spam fix. Based on size/room, not account age.
POP_GROWTH_CATCHUP_BOOST = 2.0
POP_GROWTH_CATCHUP_POP = 50_000_000
```
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/population.py:186-206`
```python
def calc_nation_growth(nation_population, comfort, rations_ratio):
    """People added to a whole nation this tick (before starvation).
    Based on the population the nation actually has, so war deaths slow it
    down; slows to POP_GROWTH_DIMINISHING_FLOOR past comfort (no hard cap).
    Small nations well below comfort grow up to 3x (POP_GROWTH_CATCHUP_*).
    (The 12h/24h growth freeze after losing a battle / being nuked was
    removed by the 2026-10-09 community vote; only real deaths count.)"""
    rations_ratio = min(1.0, max(0.0, float(rations_ratio or 0)))
    pop = max(0, int(nation_population or 0))
    pop_ratio = pop / comfort if comfort > 0 else 1
    diminishing = max(variables.POP_GROWTH_DIMINISHING_FLOOR, 1 - pop_ratio**2)
    catchup = 1 + (
        variables.POP_GROWTH_CATCHUP_BOOST
        * max(0.0, 1 - pop_ratio)
        * max(0.0, 1 - pop / variables.POP_GROWTH_CATCHUP_POP)
    )
    raw = (
        variables.POP_GROWTH_RATE * catchup * pop
        + variables.POP_GROWTH_SEED_RATE * comfort
    )
    return int(round((rations_ratio**2) * diminishing * raw))
```
**Notes:** `growth = round(rations_ratio^2 * max(0.05, 1 - (pop/comfort)^2) * (0.004 * catchup * pop + 0.00005 * comfort))`. Only written to provinces when the Pop 2.0 result is missing (population.py:702-708). Province share of nation growth is by `province_capacity_weight` (population.py:209-216) using `DEFAULT_MAX_POPULATION`, `CITY_MAX_POPULATION_ADDITION`, `LAND_MAX_POPULATION_ADDITION` (variables.py:18-20).
**Used by (grep):** `calc_nation_growth` -> `app_core/game_ticks/population.py:186`, `app_core/game_ticks/population.py:365`, `app_core/game_ticks/population.py:636`; `province_capacity_weight` -> `app_core/game_ticks/population.py:209`, `app_core/game_ticks/population.py:237`, `app_core/game_ticks/population.py:415`, `app_core/game_ticks/population.py:675`; `DEFAULT_MAX_POPULATION` -> `app_core/game_ticks/population.py:213`

### Happiness and pollution growth multipliers
**Exact rule** (verbatim) - **Source:** `variables.py:15-16`
```python
DEFAULT_HAPPINESS_GROWTH_MULTIPLIER = 0.04  # max +/-4% at happiness 100/0 (0.08% per point from 50)
DEFAULT_POLLUTION_GROWTH_MULTIPLIER = 0.02  # max +/-2% at pollution 0/100 (0.04% per point from 50)
```
**Notes:** only used inside `nation_comfort` (population.py:121-127).

## Not found / open questions
- Initial/starter population for new nations (look in signup.py; see tutorial-onboarding-misc.md).
- The DB trigger that "enforces demographics sum to population" is mentioned in a comment at population.py:717-719 but is in db/ (out of scope).
- Where `EDUCATION_GRADUATION_PRIORITY` is used.
