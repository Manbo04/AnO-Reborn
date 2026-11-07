# Food: rations, distribution, spoilage

Rations are consumed and spoiled inside the hourly `population_growth` tick (:45), not in the revenue tick. See population.md for the tick order.

## Order of operations (rations in the population tick)
1. Rations needed per province = `population // RATIONS_PER`, minimum 1, summed per user (app_core/game_ticks/population.py:581-591).
2. Distributable rations = `min(warehouse, int(covered_people // RATIONS_PER))` (population.py:609-611, 169-183).
3. Actually consumed = `min(needed, distributable)` (population.py:612).
4. Spoilage on `warehouse - consumed` (population.py:620-626), skipped during spoilage grace (population.py:595-598).
5. Deducted = consumed + spoilage (population.py:628).
6. Rations ratio = `distributable / needed` (population.py:632-635) feeds births, starvation and growth.

## Constants

### Rations per person
**What it is:** one ration feeds this many people for an hour.
**Exact rule** (verbatim) - **Source:** `variables.py:78-79`
```python
CONSUMER_GOODS_PER = 80000  # 1 Consumer good per x population
RATIONS_PER = 50000  # 1 Ration per x population (lower = more rations needed)
```
**Used by (grep):** `RATIONS_PER` -> `countries.py:719`, `countries.py:825`, `province.py:561`, `province.py:581`, `services/country_service.py:784`, `app_core/game_ticks/population.py:183` (+4 more)
**Units/range:** people per ration per hour.

### What the population tick actually charges (CONFLICT with the nation page)
**What it is:** the hourly rations the tick removes and uses as "needed".
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/population.py:583-591`
```python
        for province_row in all_provinces:
            user_id = province_row["userid"]
            curPop = province_row["population"] or 0
            rations_needed = curPop // variables.RATIONS_PER
            if rations_needed < 1:
                rations_needed = 1
            user_total_rations_needed[user_id] = (
                user_total_rations_needed.get(user_id, 0) + rations_needed
            )
```
**Notes:** CONFLICT: this tick uses `curPop // RATIONS_PER` (no age weighting, no Rationing Program). The display function `rations_needed()` in food.py uses `DEMO_RATIONS_CONSUMPTION` age weights and the Rationing Program multiplier:
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/food.py:66-76`
```python
        rationing_multiplier = (
            variables.POLICY_RATIONING_CONSUMPTION_REDUCTION
            if variables.POLICY_RATIONING_PROGRAM in policies
            else 1.0
        )

        pw_mult = variables.DEMO_RATIONS_CONSUMPTION["pop_working"]
        pc_mult = variables.DEMO_RATIONS_CONSUMPTION["pop_children"]
        pe_mult = variables.DEMO_RATIONS_CONSUMPTION["pop_elderly"]
        r_per = variables.RATIONS_PER

```
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/food.py:77-92`
```python
        if variables.FEATURE_DEMOGRAPHIC_CONSUMPTION:
            query = f"""
                SELECT COALESCE(SUM(
                    GREATEST(
                        CAST(
                            CASE WHEN pop_children IS NOT NULL THEN
                                (COALESCE(pop_working,0) * {pw_mult} + COALESCE(pop_children,0) * {pc_mult} + COALESCE(pop_elderly,0) * {pe_mult}) * {rationing_multiplier}
                            ELSE
                                FLOOR(COALESCE(population,0) / {r_per}) * {rationing_multiplier}
                            END
                        AS INTEGER),
                        1
                    )
                ), 0)
                FROM provinces WHERE userId = %s
            """
```
**Exact rule** (verbatim) - **Source:** `variables.py:140-144`
```python
DEMO_RATIONS_CONSUMPTION = {
    "pop_working": 1.0 / 50000,  # ~0.00002 rations per working person per tick
    "pop_children": 1.3 / 50000,  # 30% higher for children
    "pop_elderly": 0.8 / 50000,  # slightly lower for elderly
}
```
**Exact rule** (verbatim) - **Source:** `variables.py:357`
```python
POLICY_RATIONING_CONSUMPTION_REDUCTION = 0.85  # -15% rations consumption
```
**Notes:** Search of the repo found `POLICY_RATIONING_CONSUMPTION_REDUCTION` and `DEMO_RATIONS_CONSUMPTION` read only in app_core/game_ticks/food.py (plus scripts/); `population.py` does not reference either (grep result in "Used by" below). So the rations the tick removes ignore the Rationing Program's -15% and the 1.3x/0.8x age weights, while the nation page's "rations needed" figure includes them.
**Used by (grep):** `POLICY_RATIONING_CONSUMPTION_REDUCTION` -> `app_core/game_ticks/food.py:67`, `app_core/game_ticks/food.py:424`; `DEMO_RATIONS_CONSUMPTION` -> `app_core/game_ticks/food.py:72`, `app_core/game_ticks/food.py:73`, `app_core/game_ticks/food.py:74`, `app_core/game_ticks/food.py:433`, `app_core/game_ticks/food.py:438`, `app_core/game_ticks/food.py:443`
The tax food penalty uses a THIRD figure: total nation population // RATIONS_PER, minimum 1 (app_core/economy/tax_formula.py:42-43).

### Distribution buildings and their capacity (people reached)
**What it is:** only rations that distribution buildings can move reach people; each building reaches this many people.
**Exact rule** (verbatim) - **Source:** `variables.py:86-105`
```python
FEATURE_RATIONS_DISTRIBUTION = True  # toggle the new mechanic on/off
RATIONS_DISTRIBUTION_BUILDINGS = [
    "food_banks",
    "distribution_centers",
    "gas_stations",
    "general_stores",
    "farmers_markets",
    "malls",
]
# Tiered capacity: expensive buildings serve more population
RATIONS_DISTRIBUTION_PER_BUILDING = {
    "food_banks": 250000,  # 250k — extremely cheap
    "distribution_centers": 1500000,  # 1.5M — cheapest, purpose-built
    "gas_stations": 1000000,  # 1.0M — moderate, secondary purpose
    "general_stores": 2500000,  # 2.5M — expensive, high capacity
    "farmers_markets": 2000000,  # 2.0M — mid-tier, food-focused
    "malls": 5000000,  # 5.0M — most expensive, highest impact
}
# Convenience default for any building not in the dict
RATIONS_DISTRIBUTION_PER_BUILDING_DEFAULT = 1500000
```
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/food.py:221-231`
```python
def compute_rations_distribution_cap(building_qty_by_name):
    """Sum population served by distribution buildings (pure helper for UI/tests)."""
    total = 0
    for bname, qty in (building_qty_by_name or {}).items():
        if bname not in variables.RATIONS_DISTRIBUTION_BUILDINGS:
            continue
        per_building = variables.RATIONS_DISTRIBUTION_PER_BUILDING.get(
            bname, variables.RATIONS_DISTRIBUTION_PER_BUILDING_DEFAULT
        )
        total += int(qty or 0) * per_building
    return total
```
**Units/range:** people per building (not rations).
**Used by (grep):** `RATIONS_DISTRIBUTION_PER_BUILDING` -> `countries.py:533`, `app_core/game_ticks/population.py:172`, `app_core/game_ticks/population.py:354`, `app_core/game_ticks/population.py:568`, `app_core/game_ticks/taxes.py:361`, `app_core/game_ticks/food.py:144` (+5 more); `RATIONS_DISTRIBUTION_BUILDINGS` -> `countries.py:527`, `countries.py:730`, `app_core/game_ticks/population.py:350`, `app_core/game_ticks/food.py:225`, `app_core/game_ticks/food.py:305`; `FEATURE_RATIONS_DISTRIBUTION` -> `countries.py:519`, `province.py:568`, `province.py:712`, `province.py:830`, `services/country_service.py:830`, `app_core/game_ticks/population.py:341` (+9 more)
**Notes:** the population tick sums `qty * cap` for every building returned by its query using `RATIONS_DISTRIBUTION_PER_BUILDING_DEFAULT` for unknown names (population.py:568-571); `compute_rations_distribution_cap` (food.py) skips names not in `RATIONS_DISTRIBUTION_BUILDINGS`. The tax tick sums only the six names in its SQL (app_core/game_ticks/taxes.py:342-345).

### Overcrowding efficiency on distribution
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
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/population.py:164-183`
```python
def distribution_fix_active(now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    return now >= variables.DISTRIBUTION_FIX_START


def distributable_rations(warehouse, dist_cap, nation_population, comfort, now=None):
    """Rations that can actually reach people this tick.

    dist_cap is in PEOPLE served (RATIONS_DISTRIBUTION_PER_BUILDING), the
    warehouse is in RATIONS. Before DISTRIBUTION_FIX_START this keeps the old
    (buggy) min(warehouse, people) comparison, which almost never limited
    anything; after it, covered people are converted to rations and shrunk
    by overcrowding_efficiency()."""
    warehouse = max(0, int(warehouse or 0))
    if dist_cap is None:
        return warehouse
    if not distribution_fix_active(now):
        return min(warehouse, dist_cap)
    covered_people = dist_cap * overcrowding_efficiency(nation_population, comfort)
    return min(warehouse, int(covered_people // variables.RATIONS_PER))
```
**Units/range:** covered people = `dist_cap * overcrowding_efficiency(nation_population, comfort)`; 4x over comfort -> 50%. `DISTRIBUTION_FIX_START` (variables.py:70-72) is 2026-10-12 18:00 UTC (past), so the fixed formula is active.
**Used by (grep):** `distributable_rations` -> `app_core/game_ticks/population.py:169`, `app_core/game_ticks/population.py:359`, `app_core/game_ticks/population.py:609`; `DISTRIBUTION_FIX_START` -> `app_core/game_ticks/population2.py:171`, `app_core/game_ticks/population.py:166`, `app_core/game_ticks/population.py:173`

### Spoilage
**What it is:** banked rations above a buffer lose 2% of the excess each hour.
**Exact rule** (verbatim) - **Source:** `variables.py:107-123`
```python
# Rations spoilage: banked rations above the buffer decay each hour instead of
# sustaining unattended growth indefinitely. Every distribution building
# contributes buffer capacity, scaled the same way it scales consumption
# capacity in RATIONS_DISTRIBUTION_PER_BUILDING (~1.33x), so the buffer
# tracks real infrastructure investment regardless of which building type
# a player chose.
RATIONS_BASELINE_BUFFER_DAYS = 14
RATIONS_STORAGE_PER_BUILDING = {
    "food_banks": 333_333,
    "distribution_centers": 2_000_000,
    "gas_stations": 1_333_333,
    "general_stores": 3_333_333,
    "farmers_markets": 2_666_667,
    "malls": 6_666_667,
}
RATIONS_STORAGE_PER_BUILDING_DEFAULT = 2_000_000
RATIONS_EXCESS_DECAY_RATE = 0.02
```
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/population.py:141-161`
```python
def rations_storage_buffer(building_rows):
    """Extra rations buffer from distribution buildings.
    building_rows: iterable of (building_name, quantity)."""
    total = 0
    for bname, qty in building_rows:
        cap = variables.RATIONS_STORAGE_PER_BUILDING.get(
            bname, variables.RATIONS_STORAGE_PER_BUILDING_DEFAULT
        )
        total += (qty or 0) * cap
    return total


def rations_spoilage(remaining_after_consumption, needed, storage_buffer):
    """Rations that spoil this hour: RATIONS_EXCESS_DECAY_RATE of the stockpile
    above (baseline days of hourly need + storage buffer). Shared by the tick
    and the revenue display. Grace-period check stays with the caller."""
    buffer = needed * 24 * variables.RATIONS_BASELINE_BUFFER_DAYS + storage_buffer
    if remaining_after_consumption > buffer:
        excess = remaining_after_consumption - buffer
        return int(round(excess * variables.RATIONS_EXCESS_DECAY_RATE))
    return 0
```
**Units/range:** `buffer = needed * 24 * 14 + storage_buffer`; `spoil = int(round((stock_after_consumption - buffer) * 0.02))` when stock_after_consumption > buffer.
**Used by (grep):** `RATIONS_STORAGE_PER_BUILDING` -> `app_core/game_ticks/population.py:146`, `app_core/game_ticks/population.py:572`; `RATIONS_EXCESS_DECAY_RATE` -> `app_core/game_ticks/population.py:154`, `app_core/game_ticks/population.py:160`; `RATIONS_BASELINE_BUFFER_DAYS` -> `app_core/game_ticks/population.py:157`; `rations_spoilage` -> `countries.py:163`, `countries.py:737`, `app_core/game_ticks/population.py:153`, `app_core/game_ticks/population.py:622`
**Notes:** the grace period constant `RATIONS_SPOILAGE_GRACE_PERIOD_END` is 2026-08-28 20:00 UTC (variables.py:131-133), past.

Computed example (script output):
```
rations_spoilage(stock_after=10,000,000 needed=100 storage_buffer=1,000,000) = 179328
buffer = 100*24*14 + 1,000,000 = 1033600
distributable_rations(warehouse=1e9, dist_cap=2e6 people, pop=1e6, comfort=5e6) = 40
distributable_rations(warehouse=1e9, dist_cap=2e6 people, pop=20e6, comfort=5e6) = 20
```

### Rationing Program policy
**Exact rule** (verbatim) - **Source:** `variables.py:357-358`
```python
POLICY_RATIONING_CONSUMPTION_REDUCTION = 0.85  # -15% rations consumption
POLICY_RATIONING_HAPPINESS_PENALTY = 10  # -10 happiness per province
```
**Notes:** -15% consumption applies only in `food.py` display code (see CONFLICT above). Happiness -10 per province per hour is applied by the revenue tick (app_core/game_ticks/revenue.py:1143-1151).

### Farms and fisheries
**What it is:** the base rations producers.
**Exact rule** (verbatim) - **Source:** `variables.py:1137-1146`
```python
    "farms": {
        "money": 3000,
        "plus": {"rations": 100},
        "eff": {"pollution": 1},
    },
    "fisheries": {
        "money": 1800,
        "plus": {"rations": 160},
        "eff": {"pollution": 1},
    },
```
**Exact rule** (verbatim) - **Source:** `variables.py:76`
```python
LAND_FARM_PRODUCTION_ADDITION = 3
```
**Units/range:** farm 100 rations/h + `land * 3` per farm (revenue.py:931-933), fisheries 160 rations/h; both multiplied by productivity, bonuses and workforce (see economy-taxes-revenue.md).
**Used by (grep):** `LAND_FARM_PRODUCTION_ADDITION` -> `countries.py:421`, `province.py:615`, `app_core/game_ticks/revenue.py:932`, `app_core/economy/building_costs.py:357`

### Consumer goods retail capacity and demand
Defined in economy-taxes-revenue.md (consumer goods sections). Demographic CG per tick rates: variables.py:145-149.

## Not found / open questions
- Whether the wiki/news text says rations are demographic-weighted (not checked: docs are not trusted sources).
- Starting rations for a new nation (see tutorial-onboarding-misc.md).
