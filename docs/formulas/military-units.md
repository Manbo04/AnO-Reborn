# Military units: purchase, limits, manpower, combat stats

## Unit price, resources, manpower (where the numbers live)
### Gold price and crew per unit (code) vs resource cost (database)
**What it is:** gold price comes from `variables.MILDICT`; resource costs and `manpower_required` come from the DB table `unit_dictionary` (`production_cost_*`, `manpower_required`).
**Exact rule** (verbatim) - **Source:** `app_core/military/repositories.py:123-142`
```python
    costs = {
        "rations": int(cost_rations or 0),
        "components": int(cost_components or 0),
        "steel": int(cost_steel or 0),
        "gasoline": int(cost_fuel or 0),
        "aluminium": int(cost_aluminium or 0),
        "uranium": int(cost_uranium or 0),
    }
    costs = {k: v for k, v in costs.items() if v > 0}

    # Gold cost is currently sourced from MILDICT until dedicated DB column exists.
    gold_cost = int(mildict.get(unit_name, {}).get("price", 0) or 0)
    manpower_cost = int(
        manpower_required or mildict.get(unit_name, {}).get("manpower", 0) or 0
    )

    return {
        "unit_id": int(unit_id),
        "gold_cost": gold_cost,
        "resource_costs": costs,
```
**Exact rule** (verbatim) - **Source:** `variables.py:743-839`
```python
    "soldiers": {"price": 250, "resources": {"rations": 500}, "manpower": 1},
    "tanks": {
        "price": 7000,
        "resources": {"components": 5000, "steel": 50000, "gasoline": 2000},
        "manpower": 4,
    },
    "artillery": {
        "price": 14000,
        "resources": {"components": 3000, "steel": 30000, "gasoline": 1000},
        "manpower": 2,
    },
    "sam_batteries": {
        "price": 30000,
        "resources": {"components": 4000, "steel": 15000, "aluminium": 5000},
        "manpower": 3,
    },
    # AIR -- aluminium, not steel: planes are built from aluminium, and this
    # is the only place that made aluminium a viable resource to produce
    # (player feedback, 2026-08-16, migration 0043).
    "bombers": {
        "price": 22000,
        "resources": {"components": 15000, "aluminium": 25000, "gasoline": 8000},
        "manpower": 1,
    },
    "fighters": {
        "price": 30000,
        "resources": {"components": 10000, "aluminium": 20000, "gasoline": 5000},
        "manpower": 1,
    },
    "apaches": {
        "price": 28000,
        "resources": {"components": 8000, "aluminium": 15000, "gasoline": 3000},
        "manpower": 1,
    },
    # WATER
    "destroyers": {
        "price": 26000,
        "resources": {"steel": 120000, "components": 15000, "gasoline": 4000},
        "manpower": 6,
    },
    "cruisers": {
        "price": 48000,
        "resources": {"steel": 200000, "components": 25000, "gasoline": 6000},
        "manpower": 5,
    },
    "submarines": {
        "price": 40000,
        "resources": {"steel": 150000, "components": 20000, "gasoline": 5000},
        "manpower": 6,
    },
    # SPECIAL
    "spies": {
        "price": 25000,
        "resources": {"rations": 100, "components": 2000},
        "manpower": 0,
    },
    # Counter-intelligence (2026-09-27, migration 0085): internal security
    # force that intercepts incoming spy ops. Resource costs mirror
    # unit_dictionary.production_cost_* (which is what's actually debited).
    "counter_intel_agents": {
        "price": 30000,
        "resources": {"rations": 200, "components": 1500},
        "manpower": 1,
    },
    "icbms": {
        "price": 16000000,
        "resources": {"aluminium": 80000, "components": 50000, "gasoline": 15000},
        "manpower": 0,
    },
    "nukes": {
        "price": 80000000,
        "resources": {
            "aluminium": 120000,
            "components": 100000,
            "gasoline": 25000,
            "uranium": 20000,
        },
        "manpower": 0,
    },
    # NEW ROSTER (2026-09-05, Discord #suggestions "add kamikaze drones")
    "aircraft_carriers": {
        "price": 220000,
        "resources": {
            "steel": 400000,
            "aluminium": 200000,
            "components": 60000,
            "gasoline": 20000,
        },
        "manpower": 12,
    },
    # kamikaze_drones/cruise_missiles have no "resources" here -- those are
    # spent when drone_sites/missile_batteries manufacture the unit
    # (app_core/game_ticks/unit_production.py), not when the player activates
    # it. "price" here is the gold-only activation cost
    # (process_activate_units in app_core/military/services.py).
    "kamikaze_drones": {"price": 3500, "manpower": 0},
    "cruise_missiles": {"price": 250000, "manpower": 0},
```
**Notes:** DB-dynamic: resource costs per unit are NOT in code; the MILDICT `resources` dicts are comments-synced copies ("Resource costs synced with unit_dictionary", variables.py:742) and are not what `get_unit_costs` reads. Gold `price` IS read from MILDICT.
**Used by (grep):** `MILDICT` -> `ai_agent.py:1021`, `ai_agent.py:1039`, `ai_agent.py:1040`, `ai_agent.py:1060`, `ai_agent.py:1061`, `app.py:37` (+11 more)

### Buy / sell / activate
**Exact rule** (verbatim) - **Source:** `app_core/military/services.py:116-125`
```python
PROPAGANDA_SOLDIER_PRICE_FACTOR = 0.65  # Widespread Propaganda: soldiers cost 35% less


def _unit_gold_price(cId, units, price, db):
    """Gold price per unit for this player. Widespread Propaganda discounts
    soldiers (the military page already showed the discounted price but the
    purchase charged full). Buy and sell share this so there is no
    buy-cheap/sell-full arbitrage."""
    if units == "soldiers" and get_upgrades(cId, db=db).get("widespreadpropaganda"):
        return int(price * PROPAGANDA_SOLDIER_PRICE_FACTOR)
```
**Exact rule** (verbatim) - **Source:** `app_core/military/services.py:153-158`
```python
    totalPrice = wantedUnits * price
    
    sell_deltas = {res: wantedUnits * amt for res, amt in resources.items()}
    adjust_resources_batch(db, cId, sell_deltas)
    
    remove_units(db, cId, unit_id, wantedUnits)
```
**Exact rule** (verbatim) - **Source:** `app_core/military/services.py:164-190`
```python
def process_buy_units(db, cId, units, wantedUnits, mildict):
    # Same race found in process_sell_units above, mirror image: two
    # concurrent buy requests both read the same gold/manpower/resource
    # balances before either commits, both pass their affordability check,
    # and both call add_units() unconditionally -- update_manpower_and_gold's
    # GREATEST(0, ...) clamp stops gold from going negative, but does
    # nothing to stop the second request's add_units() call, so a raced
    # double-buy grants double the units for a single purchase's worth of
    # gold/resources. Serializing here matches build_structure's advisory
    # lock in action_loop.py.
    db.execute("SELECT pg_advisory_xact_lock(%s)", (cId,))

    unit_costs = get_unit_costs(db, units, mildict)
    if not unit_costs:
        return False, "Unit definition not found or inactive"

    units_dict, _ = get_user_units_with_stats(db, cId)
    limits = compute_display_limits(cId, db, units_dict)
    
    if wantedUnits > limits[units]:
        return False, f"Unit buy limit exceeded (allowed {limits[units]})"

    manpower_available, gold = get_manpower_and_gold(db, cId)
    price = _unit_gold_price(cId, units, unit_costs["gold_cost"], db)
    totalPrice = wantedUnits * price

    if totalPrice > gold:
```
**Notes:** SELL refunds 100% of gold price, 100% of resource costs and the manpower (services.py:153-158 `totalPrice`, `sell_deltas`). Soldiers cost x0.65 with the Widespread Propaganda upgrade (services.py:116 `PROPAGANDA_SOLDIER_PRICE_FACTOR`). Buying checks, in order: building limit, gold, crew cap, recruitment manpower, each resource.

### Building-based unit limits
**Exact rule** (verbatim) - **Source:** `app_core/military/services.py:25-31`
```python
CARRIER_AIR_CAPACITY_BONUS = 500

# Spy/counter-intel capacity per admin building (see compute_display_limits).
SPIES_PER_ADMIN_BUILDING = 10
# SAM batteries (air defense, migration 0084) are housed at army bases.
SAM_BATTERIES_PER_ARMY_BASE = 20
COUNTER_INTEL_PER_ADMIN_BUILDING = 10
```
**Exact rule** (verbatim) - **Source:** `app_core/military/services.py:44-62`
```python
    soldiers = max(0, army_bases * 5000 - military["soldiers"])
    tanks = max(0, army_bases * 200 - military["tanks"])
    artillery = max(0, army_bases * 200 - military["artillery"])
    sam_batteries = max(0, army_bases * SAM_BATTERIES_PER_ARMY_BASE - military["sam_batteries"])

    # Air units share aerodome capacity, extended by any carriers owned
    air_units = military["fighters"] + military["bombers"] + military["apaches"]
    air_capacity = aerodomes * 100 + military["aircraft_carriers"] * CARRIER_AIR_CAPACITY_BONUS
    air_limit = max(0, air_capacity - air_units)
    bombers = air_limit
    fighters = air_limit
    apaches = air_limit

    # Naval units
    naval_units = military["submarines"] + military["destroyers"]
    naval_limit = max(0, harbours * 20 - naval_units)
    submarines = naval_limit
    destroyers = naval_limit
    cruisers = max(0, harbours * 10 - military["cruisers"])
```
**Exact rule** (verbatim) - **Source:** `app_core/military/services.py:75-86`
```python
    )
    icbms = max(0, silos + 1 - military["icbms"])
    nukes = max(0, silos - military["nukes"])

    upgrades = get_upgrades(cId, db=db)
    if upgrades.get("increasedfunding"):
        spies = int(spies * 1.4)

    if not upgrades.get("icbmsilo"):
        icbms = 0

    if not upgrades.get("nucleartestingfacility"):
```
**Units/range:** soldiers 5000/army base, tanks and artillery 200/army base, SAM 20/army base, air units share `aerodomes*100 + carriers*500`, subs+destroyers share `harbours*20`, cruisers `harbours*10`, carriers 1/harbour, spies and counter-intel 10/admin building, icbms `silos+1`, nukes `silos`. Icbms need upgrade `icbmsilo` (else 0), nukes need `nucleartestingfacility` (else 0), spies x1.4 with `increasedfunding`.

### Crew cap (manpower) = 10% of working population
**Exact rule** (verbatim) - **Source:** `app_core/military/manpower.py:21-40`
```python
UNIT_MANPOWER_CREW = _crew_table()

MANPOWER_SHARE = 0.10


def unit_crew_requirement(unit_name: str) -> int:
    """Return crew / manpower needed per unit."""
    return UNIT_MANPOWER_CREW.get(unit_name, 0)


def calc_manpower_cap(pop_working: int, population: int = 0) -> int:
    """Calculate the maximum manpower allowed for a nation.

    Cap = MANPOWER_SHARE (10%) of the nation's working-age population
    (pop_working summed over provinces; fall back to population if absent or 0).
    """
    effective_pop = int(pop_working or 0)
    if effective_pop <= 0:
        effective_pop = int(population or 0)
    return max(0, int(effective_pop * MANPOWER_SHARE))
```
**Exact rule** (verbatim) - **Source:** `app_core/military/manpower.py:61-72`
```python
def can_recruit(
    unit_name: str, count: int, current_used: int, cap: int
) -> tuple[bool, int, int]:
    """Check if recruiting `count` of `unit_name` is within manpower cap.

    Returns:
        (allowed, needed_crew, free_crew)
    """
    needed_crew = int(count or 0) * unit_crew_requirement(unit_name)
    free_crew = calc_free_manpower(cap, current_used)
    allowed = (current_used + needed_crew) <= cap
    return allowed, needed_crew, free_crew
```
**Units/range:** cap = int(10% of summed `pop_working`, fallback population); used = sum(units * MILDICT manpower). Unconditional-surrender penalty multiplies the cap by 0.5 for 5 days (wars/rules.py:35-36).

### Recruitment manpower pool (stats.manpower)
**Exact rule** (verbatim) - **Source:** `tasks.py:204-228`
```python
            manpower_map[row["id"]] = row["manpower"]

        # Manpower tracks a moving target tied to current population (the
        # eligible military-age pool), rather than accumulating forever.
        # Each tick it moves partway toward that target in either direction:
        # up when population has grown and there's room to recruit more,
        # down when population has shrunk (attrition/aging out of the
        # reserve), instead of only ever increasing until spent.
        ADJUSTMENT_RATE = 0.15
        ELIGIBLE_POOL_FRACTION = 0.2

        manpower_updates = []
        for user_id in user_ids:
            population = pop_map.get(user_id)
            if not population:
                continue

            target_manpower = float(population) * ELIGIBLE_POOL_FRACTION
            manpower = manpower_map.get(user_id, 0)
            delta = int((target_manpower - manpower) * ADJUSTMENT_RATE)

            if delta != 0:
                manpower_updates.append((delta, user_id))

        # Batch update all manpower at once
```
**Units/range:** every 4h (celery_schedule.py:116) manpower moves 15% of the way toward 20% of total population (up or down).

## Combat stats per unit (units.py)
Damage per unit and the type-matchup bonus. `bonus` is added per attacking unit amount against each defending unit type.
**Exact rule** (verbatim) - **Source:** `units.py:78-81`
```python
class SoldierUnit(BlueprintUnit):
    unit_type = "soldiers"
    damage = 1
    resource_cost = {"ammunition": 1}
```
**Exact rule** (verbatim) - **Source:** `units.py:98-114`
```python
class TankUnit(BlueprintUnit):
    unit_type = "tanks"
    damage = 40
    resource_cost = {"ammunition": 1, "gasoline": 1}

    def __init__(self, amount):
        self.amount = amount

    def attack(self, defending_units):
        # One tank beats 4 soldiers. If one tank beat only 4 soldiers then
        # soldiers would counter tanks (1 tank costs ~50 soldiers). One tank is
        # therefore modeled as 4x more effective vs soldiers.
        if defending_units == "soldiers":
            self.damage += 2
            self.bonus += 6 * self.amount

        return [self.damage * self.amount, self.bonus]
```
**Exact rule** (verbatim) - **Source:** `units.py:120-132`
```python
class ArtilleryUnit(BlueprintUnit):
    unit_type = "artillery"
    damage = 80
    resource_cost = {"ammunition": 2}

    def __init__(self, amount):
        self.amount = amount

    def attack(self, defending_units):
        # One artillery beats 3 tanks
        if defending_units == "tanks":
            self.bonus += 2 * self.amount
        return [self.damage * self.amount, self.bonus]
```
**Exact rule** (verbatim) - **Source:** `units.py:138-164`
```python
class BomberUnit(BlueprintUnit):
    unit_type = "bombers"
    damage = 100
    resource_cost = {"ammunition": 2, "gasoline": 2}

    def __init__(self, amount):
        self.amount = amount

    def attack(self, defending_units):
        if defending_units == "soldiers":
            self.bonus += 2 * self.amount

        # Micro randomization
        # One bomber beats random number of tanks (where they drop the bombs)
        # between 2 and 6
        if defending_units == "tanks":
            self.bonus += randint(2, 6) * self.amount
            # self.bonus += 2 * self.amount

        if defending_units == "destroyers":
            self.bonus += 2 * self.amount
        if defending_units == "submarines":
            self.bonus += 2 * self.amount
        return [self.damage * self.amount, self.bonus]

    def buy(amount):
        pass
```
**Exact rule** (verbatim) - **Source:** `units.py:167-184`
```python
class FighterUnit(BlueprintUnit):
    unit_type = "fighters"
    damage = 100
    resource_cost = {"ammunition": 2, "gasoline": 2}

    def __init__(self, amount):
        self.amount = amount

    def attack(self, defending_units):
        if defending_units == "bombers":
            # self.damage += 55
            self.bonus += 4 * self.amount
        elif defending_units == "apaches":
            self.bonus += 3 * self.amount
        return [self.damage * self.amount, self.bonus]

    def buy(amount):
        pass
```
**Exact rule** (verbatim) - **Source:** `units.py:187-203`
```python
class ApacheUnit(BlueprintUnit):
    unit_type = "apaches"
    damage = 100
    resource_cost = {"ammunition": 2, "gasoline": 2}

    def __init__(self, amount):
        self.amount = amount

    def attack(self, defending_units):
        if defending_units == "soldiers":
            self.bonus += 1 * self.amount
        elif defending_units == "tanks":
            self.bonus += 1 * self.amount
        return [self.damage * self.amount, self.bonus]

    def buy():
        pass
```
**Exact rule** (verbatim) - **Source:** `units.py:206-220`
```python
class DestroyerUnit(BlueprintUnit):
    unit_type = "destroyers"
    damage = 100
    resource_cost = {"ammunition": 2, "gasoline": 2}

    def __init__(self, amount):
        self.amount = amount

    def attack(self, defending_units):
        if defending_units == "submarines":
            self.bonus += 1.6 * self.amount
        return [self.damage * self.amount, self.bonus]

    def buy(amount):
        pass
```
**Exact rule** (verbatim) - **Source:** `units.py:223-241`
```python
class CruiserUnit(BlueprintUnit):
    unit_type = "cruisers"
    damage = 200
    resource_cost = {"ammunition": 2, "gasoline": 2}

    def __init__(self, amount):
        self.amount = amount

    def attack(self, defending_units):
        if defending_units == "destroyers":
            self.bonus += 0.3 * self.amount
        elif defending_units == "fighters":
            self.bonus += 0.1 * self.amount
        elif defending_units == "apaches":
            self.bonus += 0.4 * self.amount
        return [self.damage * self.amount, self.bonus]

    def buy(amount):
        pass
```
**Exact rule** (verbatim) - **Source:** `units.py:244-258`
```python
class SubmarineUnit(BlueprintUnit):
    unit_type = "submarines"
    damage = 100
    resource_cost = {"ammunition": 2, "gasoline": 2}

    def __init__(self, amount):
        self.amount = amount

    def attack(self, defending_units):
        if defending_units == "cruisers":
            self.bonus += 0.2 * self.amount
        return [self.damage * self.amount, self.bonus]

    def buy():
        pass
```
**Exact rule** (verbatim) - **Source:** `units.py:261-278`
```python
class CarrierUnit(BlueprintUnit):
    unit_type = "aircraft_carriers"
    damage = 300
    resource_cost = {"ammunition": 2, "gasoline": 4}

    def __init__(self, amount):
        self.amount = amount

    def attack(self, defending_units):
        if defending_units == "submarines":
            self.bonus -= 0.3 * self.amount
        elif defending_units in ("fighters", "bombers", "apaches"):
            self.bonus += 0.3 * self.amount
        return [self.damage * self.amount, self.bonus]

    def buy():
        pass

```
**Exact rule** (verbatim) - **Source:** `units.py:281-314`
```python
class IcbmUnit(BlueprintUnit):
    unit_type = "icbms"
    damage = 1000

    def __init__(self, amount):
        self.amount = amount

    def attack(self, defending_units):
        if defending_units == "submarines":
            self.bonus -= 5 * self.amount
        return [self.damage * self.amount, self.bonus]

    def buy():
        pass


class NukeUnit(BlueprintUnit):
    unit_type = "nukes"
    damage = 3000

    def __init__(self, amount):
        self.amount = amount

    def attack(self, defending_units):
        if defending_units == "submarines":
            self.bonus -= 5 * self.amount
        else:
            pass
        return [self.damage * self.amount, self.bonus]

    def buy():
        pass


```
**Notes:** the class attribute `resource_cost` (ammunition/gasoline per unit) is never read anywhere else (grep: no references outside units.py), so combat does not consume ammo per attack. Tank damage becomes 42 vs soldiers (units.py:111). Bomber vs tanks uses `randint(2, 6)` (units.py:149-150, random each call). Unusable units (maintenance resource stock exactly 0) contribute 0 (units.py:13-38, 498-499 in `Units.attack`).

### Drone sites / missile batteries stockpile
**Exact rule** (verbatim) - **Source:** `variables.py:847-865`
```python
UNIT_STOCKPILE_BUILDINGS = {
    "drone_sites": {
        "unit": "kamikaze_drones",
        "cap_per_building": 10,  # matches building_dictionary.effect_value
        "production_per_tick": 1,
        "resource_cost": {"components": 400, "aluminium": 800},
    },
    "missile_batteries": {
        "unit": "cruise_missiles",
        "cap_per_building": 5,
        "production_per_tick": 1,
        "resource_cost": {"components": 8000, "aluminium": 12000, "steel": 5000},
    },
}

UNIT_LAUNCH_FUEL_COST = {
    "kamikaze_drones": 150,
    "cruise_missiles": 2000,
}
```
**Notes:** produced by the hourly tick `produce_unit_stockpiles` (:35); tick code not read (see Not covered).

### Iron Dome (province interceptors)
**Exact rule** (verbatim) - **Source:** `app_core/military/iron_dome.py:16-19`
```python
MAX_DOMES_PER_PROVINCE = 10
DOME_GOLD_COST = 250_000
DOME_RESOURCE_COSTS = {"components": 6000, "steel": 20000, "aluminium": 8000}
DOME_UPKEEP_GASOLINE = 20  # per dome per military-maintenance tick (hourly)
```
**Exact rule** (verbatim) - **Source:** `wars/air_defense.py:45-70`
```python
IRON_DOME_CAPS = {
    "kamikaze_drones": 0.85,
    "cruise_missiles": 0.75,
    "icbms": 0.50,
    "nukes": 0.50,
}
IRON_DOME_SOFTNESS = 4.0  # 4 domes -> ~63% of cap, 10 (max) -> ~92% of cap
STAR_WARS_BONUS = 1.25
STAR_WARS_HARD_CAP = 0.95


def calculate_iron_dome_interception(dome_count, projectile_type: str,
                                     has_star_wars: bool = False, rng=None) -> float:
    """Chance (0..1) that a province's Iron Domes shoot down an incoming
    projectile. Diminishing returns per dome; the Star Wars Project tech
    multiplies the result by 1.25."""
    cap = IRON_DOME_CAPS.get(projectile_type)
    if cap is None or not dome_count or dome_count <= 0:
        return 0.0
    rng = rng or random
    pct = cap * (1.0 - math.exp(-float(dome_count) / IRON_DOME_SOFTNESS))
    pct *= rng.uniform(0.9, 1.1)
    pct = min(cap, max(0.0, pct))
    if has_star_wars:
        pct = min(STAR_WARS_HARD_CAP, pct * STAR_WARS_BONUS)
    return pct
```
**Units/range:** max 10 per province; 250,000 gold + components 6000, steel 20000, aluminium 8000; dismantle refunds 50% gold (iron_dome.py:20); upkeep 20 gasoline/dome/hour.

### SAM interception (drones / cruise missiles only)
**Exact rule** (verbatim) - **Source:** `wars/air_defense.py:4-39`
```python
def calculate_sam_interception(sam_count: int, projectile_type: str, rng=None) -> float:
    """
    Calculate the percentage of incoming projectiles (drones/missiles)
    intercepted by SAM batteries.
    
    Diminishing returns and hard cap.
    """
    if sam_count <= 0:
        return 0.0
        
    rng = rng or random
    
    # Base effectiveness scales with SAM count
    # 10 SAMs -> ~25%
    # 50 SAMs -> ~71%
    # 100 SAMs -> ~92% (before cap)
    softness = 35.0
    base_interception = 1.0 - math.exp(-sam_count / softness)
    
    # Cap depending on projectile
    if projectile_type == 'kamikaze_drones':
        max_interception = 0.90
        # drones are slower, easier to intercept
    elif projectile_type == 'cruise_missiles':
        max_interception = 0.80
        # cruise missiles are faster, harder to intercept
    else:
        return 0.0
        
    interception_pct = min(max_interception, base_interception)
    
    # Add a little variance
    variance = rng.uniform(0.9, 1.1)
    final_pct = interception_pct * variance
    
    return min(max_interception, max(0.0, final_pct))
```
## Not found / open questions
- Live `unit_dictionary` values (DB). Seed history is in migrations 0007/0014/0019/0066/0084/0085 (not read).
- `produce_unit_stockpiles` tick source (app_core/game_ticks/unit_production.py) not read.
