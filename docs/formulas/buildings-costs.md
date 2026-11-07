# Buildings: build cost, sell refund, land/cities/provinces

## Order of operations (buying a building)
1. `build_structure` locks the user (advisory lock), checks the building is `is_active` and that any `required_tech_id` is unlocked (action_loop.py:59-78).
2. `purchase_building` applies the policy gold discount and charges gold and resources (app_core/economy/building_purchase.py:120-124).
3. Land/city purchases use `land_city_purchase_cost` (app_core/economy/building_costs.py:458-475).
Selling a building runs `demolish_structure` (action_loop.py:99-209).

## Build cost tables

### Build costs: gold + resources per building
**What it is:** the canonical build price. `get_build_cost` reads `<name>_price` and `<name>_resource` from this dict; the DB `building_dictionary` row is NOT used for the amount (building_costs.py docstring line 1 and 163-194).
**Exact rule** (verbatim) - **Source:** `variables.py:867-990`
```python
PROVINCE_UNIT_PRICES = {
    "land_price": 0,
    "cityCount_price": 0,
    # Power Generation (Tier 2-3)
    "coal_burners_price": 2500000,
    "coal_burners_resource": {"lumber": 40000},
    "oil_burners_price": 4500000,
    "oil_burners_resource": {"lumber": 60000, "iron": 20000},
    "hydro_dams_price": 35000000,
    "hydro_dams_resource": {"steel": 180000, "aluminium": 90000},
    "nuclear_reactors_price": 150000000,
    "nuclear_reactors_resource": {"steel": 500000},
    "solar_fields_price": 8000000,
    "solar_fields_resource": {"copper": 40000, "bauxite": 30000},
    "wind_farms_price": 4000000,
    "wind_farms_resource": {"copper": 20000, "bauxite": 15000},
    "geothermal_plants_price": 12000000,
    "geothermal_plants_resource": {"copper": 60000, "bauxite": 45000},
    # Retail / Consumer Goods (Tier 2-3)
    "gas_stations_price": 7000000,
    "gas_stations_resource": {"steel": 75000, "aluminium": 50000},
    "general_stores_price": 15000000,
    "general_stores_resource": {"steel": 90000, "aluminium": 105000},
    "farmers_markets_price": 4500000,
    "farmers_markets_resource": {"steel": 110000, "aluminium": 120000},
    "malls_price": 225000000,
    "malls_resource": {"steel": 540000, "aluminium": 360000},
    "banks_price": 120000000,
    "banks_resource": {"steel": 340000, "aluminium": 165000},
    "industrial_district_price": 280000000,
    "industrial_district_resource": {"steel": 800000, "components": 200000},
    "workshops_price": 3000000,
    "workshops_resource": {"lumber": 20000, "steel": 5000},
    "jewelry_stores_price": 45000000,
    "jewelry_stores_resource": {"steel": 80000, "aluminium": 40000},
    "automotive_plants_price": 350000000,
    "automotive_plants_resource": {"steel": 900000, "aluminium": 500000, "components": 250000},
    # Distribution Centers (Tier 1 — key early-game building for rations/CG flow)
    "food_banks_price": 250000,
    "food_banks_resource": {"lumber": 10000},
    "distribution_centers_price": 2500000,
    "distribution_centers_resource": {"lumber": 25000, "iron": 5000},
    # Public Works (Tier 2-3)
    "city_parks_price": 4500000,
    "city_parks_resource": {"steel": 22000},
    "hospitals_price": 30000000,
    "hospitals_resource": {"steel": 210000, "aluminium": 130000},
    "libraries_price": 10000000,
    "libraries_resource": {"steel": 85000, "aluminium": 60000},
    "universities_price": 40000000,
    "universities_resource": {"steel": 150000, "aluminium": 80000},
    "monorails_price": 250000000,
    "monorails_resource": {"steel": 600000, "aluminium": 300000},
    "railways_price": 62500000,
    "railways_resource": {"steel": 150000, "aluminium": 75000},
    "metros_price": 150000000,
    "metros_resource": {"steel": 300000, "aluminium": 150000},
    "firewatch_towers_price": 15000,
    "firewatch_towers_resource": {"steel": 200, "lumber": 1000},
    "levees_price": 75000,
    "levees_resource": {"steel": 3000},
    "seismic_reinforcements_price": 150000,
    "seismic_reinforcements_resource": {"steel": 5000, "aluminium": 1000},
    # Education Buildings (Tier 2)
    # Halved 10-27 (weekly vote "cheaper education buildings"): the first
    # schools were a soft-lock for nations without spare steel.
    "primary_school_price": 2000000,
    "primary_school_resource": {"steel": 12000, "aluminium": 7500, "lumber": 20000},
    "high_school_price": 6000000,
    "high_school_resource": {"steel": 30000, "aluminium": 20000, "lumber": 40000},
    # Military Infrastructure (Tier 2-4)
    "army_bases_price": 8000000,
    "army_bases_resource": {"lumber": 120000},
    "harbours_price": 18000000,
    "harbours_resource": {"steel": 320000},
    "aerodomes_price": 22000000,
    "aerodomes_resource": {"aluminium": 60000, "steel": 250000},
    "admin_buildings_price": 50000000,
    "admin_buildings_resource": {"steel": 135000, "aluminium": 110000},
    "silos_price": 350000000,
    "silos_resource": {"steel": 1080000, "aluminium": 480000},
    "drone_sites_price": 15000000,
    "drone_sites_resource": {"components": 200000, "steel": 150000, "aluminium": 100000},
    "missile_batteries_price": 120000000,
    "missile_batteries_resource": {"steel": 600000, "aluminium": 300000, "components": 150000},
    # Resource Extraction (Tier 1)
    # ALL must be buildable with raw Tier-0/1 resources only
    "farms_price": 1500000,
    "farms_resource": {"lumber": 30000},
    "pumpjacks_price": 3000000,
    "pumpjacks_resource": {"iron": 22000},
    "coal_mines_price": 3500000,
    "coal_mines_resource": {"lumber": 45000},
    "bauxite_mines_price": 2400000,
    "bauxite_mines_resource": {"lumber": 30000},
    "copper_mines_price": 2800000,
    "copper_mines_resource": {"lumber": 38000},
    "uranium_mines_price": 5500000,
    "uranium_mines_resource": {"iron": 35000, "lumber": 25000},
    "lead_mines_price": 2600000,
    "lead_mines_resource": {"lumber": 38000},
    "iron_mines_price": 3800000,
    "iron_mines_resource": {"lumber": 30000},
    "lumber_mills_price": 2200000,
    "fisheries_price": 800000,
    "fisheries_resource": {"lumber": 15000},
    "silver_mines_price": 4000000,
    "silver_mines_resource": {"lumber": 35000},
    "bullion_mines_price": 5000000,
    "bullion_mines_resource": {"lumber": 40000, "iron": 10000},
    "diamond_mines_price": 6000000,
    "diamond_mines_resource": {"lumber": 40000, "iron": 15000},
    # Processing (Tier 2) — steel_mills/aluminium_refineries use only Tier 1 raws
    "component_factories_price": 16000000,
    "component_factories_resource": {"steel": 30000, "aluminium": 30000, "lumber": 80000},
    "steel_mills_price": 6000000,
    "steel_mills_resource": {"iron": 60000, "coal": 40000, "lumber": 30000},
    "ammunition_factories_price": 10000000,
    "ammunition_factories_resource": {"iron": 25000, "copper": 15000},
    "aluminium_refineries_price": 5500000,
    "aluminium_refineries_resource": {"iron": 40000, "lumber": 20000},
    "oil_refineries_price": 9000000,
    "oil_refineries_resource": {"iron": 30000, "lumber": 15000},
}
```
**Exact rule** (verbatim) - **Source:** `app_core/economy/building_costs.py:163-194`
```python
def get_build_cost(building_name: str, policies: list | None = None) -> dict:
    """Return gold, resources, and a player-facing display string."""
    name = _normalize_building_name(building_name)
    prices = variables.PROVINCE_UNIT_PRICES
    price_key = f"{name}_price"
    if price_key not in prices:
        raise KeyError(f"Unknown building: {building_name}")

    gold = apply_policy_gold_discount(name, prices[price_key], policies)
    resources = dict(prices.get(f"{name}_resource") or {})
    display_name = BUILDING_DISPLAY_NAMES.get(
        name, name.replace("_", " ").capitalize()
    )

    parts = [f"${format_money(gold)}"]
    for res, amt in resources.items():
        parts.append(f"{format_weight(amt)} {res.replace('_', ' ')}")
    if len(parts) == 1:
        cost_display = f"{display_name} cost ${format_money(gold)} each"
    else:
        resource_text = ", ".join(parts[1:])
        cost_display = (
            f"{display_name} cost ${format_money(gold)}, {resource_text} each"
        )

    return {
        "name": name,
        "display_name": display_name,
        "gold": int(gold),
        "resources": resources,
        "cost_display": cost_display,
    }
```
**Units/range:** gold and resource units per ONE building.
**Used by (grep):** `PROVINCE_UNIT_PRICES` -> `province.py:675`, `province.py:1919`, `province.py:2328`, `province.py:2577`, `province.py:2667`, `province.py:2768` (+7 more); `get_build_cost` -> `province.py:46`, `province.py:2337`, `province.py:2374`, `province.py:2741`, `app.py:1314`, `app.py:1322` (+3 more)
**Notes:** `lumber_mills` has `lumber_mills_price` (line 970) but NO `lumber_mills_resource` key: it costs gold only (the code does `prices.get(f"{name}_resource") or {}`). Verified by script (see "Consistency checks" below). Comment "Halved 10-27" at variables.py:931 describes only the two school entries; the numbers on lines 933-936 are what the code uses.

### Policy gold discounts on building prices
**What it is:** the gold price is multiplied by policy-dependent factors; the policy numbers are IDs from the `policies.education` array.
**Exact rule** (verbatim) - **Source:** `app_core/economy/building_costs.py:151-160`
```python
def apply_policy_gold_discount(building_name: str, gold: float, policies: list | None) -> float:
    policies = policies or []
    price = float(gold)
    if 2 in policies:
        price *= 0.96
    if 6 in policies and building_name == "universities":
        price *= 0.93
    if 1 in policies and building_name == "universities":
        price *= 1.14
    return price
```
**Units/range:** `2 in policies` -> x0.96 on EVERY building and on land/cities; `6 in policies` and universities -> x0.93; `1 in policies` and universities -> x1.14.
**Used by (grep):** `apply_policy_gold_discount` -> `province.py:1956`, `province.py:1957`, `action_loop.py:115`, `action_loop.py:166`, `app_core/economy/building_costs.py:151`, `app_core/economy/building_costs.py:171` (+3 more)
**Notes:** CONFLICT: policy 2 is named "Mandatory Schooling (2): Graduation rates +50%, Happiness +3 per province" on the country page (templates/country.html, policy list; see tech-upgrades-policies.md), and policy 1 is "Universal Healthcare". Neither description mentions -4% building gold or +14% university cost. Policy 6 "University Grants: Universities cost 7% less" matches x0.93. The same hardcoded numbers are duplicated at province.py:1971-1976 and province.py:2580-2585, and the policy array read is `SELECT education FROM policies` (app_core/economy/building_purchase.py:66-74).

### Sell refund
**What it is:** selling a building gives back the (policy-discounted) gold price AND all of its resources, 100%.
**Exact rule** (verbatim) - **Source:** `action_loop.py:164-186`
```python
        prices = variables.PROVINCE_UNIT_PRICES
        policies = _load_policies(db, user_id)
        unit_gold = apply_policy_gold_discount(
            building_name, prices.get(f"{building_name}_price", 0), policies
        )
        refund_gold = int(unit_gold) * quantity
        if refund_gold:
            db.execute(
                "UPDATE stats SET gold = gold + %s WHERE id=%s",
                (refund_gold, user_id),
            )

        for resource, per_unit in (prices.get(f"{building_name}_resource") or {}).items():
            qty = int(per_unit) * quantity
            db.execute(
                """
                INSERT INTO user_economy (user_id, resource_id, quantity)
                SELECT %s, resource_id, %s FROM resource_dictionary WHERE name=%s
                ON CONFLICT (user_id, resource_id)
                DO UPDATE SET quantity = user_economy.quantity + EXCLUDED.quantity
                """,
                (user_id, qty, resource),
            )
```
**Units/range:** refund_gold = `int(unit_gold) * quantity`; resource refund = `int(per_unit) * quantity` per resource.
**Used by (grep):** `demolish_structure` -> `province.py:1171`, `province.py:1173`, `province.py:1304`, `province.py:1306`, `action_loop.py:99`
**Notes:** the refund is NOT 75%. `SELL_REFUND_RATIO = 0.75` applies only to selling land/cities in the province route:
**Exact rule** (verbatim) - **Source:** `province.py:1921`
```python
        SELL_REFUND_RATIO = 0.75  # 75% refund on sell to prevent arbitrage
```
**Exact rule** (verbatim) - **Source:** `province.py:1957-1958`
```python
            discounted_price = apply_policy_gold_discount(units, raw_price, policies)
            totalPrice = max(0, int(discounted_price * SELL_REFUND_RATIO))
```
Note `demolish_structure` credits gold with a raw `UPDATE stats SET gold = gold + %s` (action_loop.py:171-174), not through `ledger`.
Selling buildings is blocked while the nation has any war with `peace_date IS NULL` (as attacker or defender):
**Exact rule** (verbatim) - **Source:** `province.py:2005-2020`
```python
        # Targetable buildings can be sold for a 75% refund. Lock building
        # liquidation during an active war so defenders cannot cash out the
        # exact infrastructure an opponent is paying attack actions to destroy.
        if way == "sell" and units not in ("land", "cityCount"):
            db.execute(
                "SELECT 1 FROM wars WHERE (attacker = %s OR defender = %s) "
                "AND peace_date IS NULL LIMIT 1",
                (cId, cId),
            )
            if db.fetchone():
                return _province_error(
                    400,
                    "Buildings cannot be sold while you are at war. "
                    "Resolve the war through peace or its normal outcome first.",
                )

```
STALE COMMENT: province.py:2005 says "Targetable buildings can be sold for a 75% refund", but the code on this route credits `totalPrice` (100% of discounted gold, `wantedUnits * price`, province.py:1970-1977) plus 100% of resources (province.py:2060-2067 `credit_resources`). The mass-sell path has the same war check (province.py:2569). The single-building route `/build_structure` with a negative quantity calls `demolish_structure` (province.py:1304-1311), which has NO war check in action_loop.py:99-209. No war check appears in `build_structure_action` between its start (province.py:1264) and the `demolish_structure` call (province.py:1304-1311), so a negative `quantity` posted to `/build_structure` appears to bypass the war sell lock; this was not exercised live.

### Building classes (which slot a building uses)
**What it is:** "city" buildings need city slots, "land" buildings need land slots.
**Exact rule** (verbatim) - **Source:** `app_core/economy/building_costs.py:17-80`
```python
CITY_UNITS = frozenset(
    {
        "coal_burners",
        "oil_burners",
        "hydro_dams",
        "nuclear_reactors",
        "solar_fields",
        "wind_farms",
        "geothermal_plants",
        "gas_stations",
        "general_stores",
        "farmers_markets",
        "malls",
        "banks",
        "distribution_centers",
        "food_banks",
        "city_parks",
        "hospitals",
        "libraries",
        "universities",
        "monorails",
        "railways",
        "metros",
        "primary_school",
        "high_school",
        "industrial_district",
        "workshops",
        "jewelry_stores",
        "automotive_plants",
    }
)

LAND_UNITS = frozenset(
    {
        "army_bases",
        "harbours",
        "aerodomes",
        "admin_buildings",
        "silos",
        "drone_sites",
        "missile_batteries",
        "farms",
        "fisheries",
        "pumpjacks",
        "coal_mines",
        "bauxite_mines",
        "copper_mines",
        "uranium_mines",
        "lead_mines",
        "iron_mines",
        "lumber_mills",
        "silver_mines",
        "diamond_mines",
        "bullion_mines",
        "component_factories",
        "steel_mills",
        "ammunition_factories",
        "aluminium_refineries",
        "oil_refineries",
        "firewatch_towers",
        "levees",
        "seismic_reinforcements",
    }
)
```
**Used by (grep):** `CITY_UNITS` -> `ai_agent.py:331`, `province.py:43`, `province.py:383`, `province.py:1876`, `province.py:2753`, `services/province_service.py:3` (+10 more); `LAND_UNITS` -> `ai_agent.py:332`, `province.py:44`, `province.py:384`, `province.py:1878`, `province.py:2753`, `services/province_service.py:3` (+8 more); `get_slot_type` -> `app_core/economy/building_costs.py:197`, `app_core/economy/building_purchase.py:12`, `app_core/economy/building_purchase.py:144`

## Land, cities, provinces

### Land and city price (per province, linear with cap)
**What it is:** the nth city or land in a province costs base + increment * owned, up to a ceiling.
**Exact rule** (verbatim) - **Source:** `app_core/economy/building_costs.py:423-429`
```python
# Land / city expansion pricing. Each extra city or land costs a bit more
# than the last (linear), up to a price ceiling after CAP_THRESHOLD owned.
LAND_CITY_PRICING = {
    # unit: (base_price, increment_per_owned, cap_threshold)
    "cityCount": (750000, 50000, 200),
    "land": (520000, 25000, 100),
}
```
**Exact rule** (verbatim) - **Source:** `app_core/economy/building_costs.py:432-455`
```python
def sum_cost_capped_linear(
    base_price, increment_per_item, current_owned, num_purchased, cap_threshold
):
    """Linear pricing with a hard cap: O(1) closed-form calculation.
    Sum over i=0..n-1 of min(basePrice + (currentOwned + i) * increment, MaxPrice).
    """
    max_price = base_price + (cap_threshold * increment_per_item)
    total_cost = 0

    # Units bought BEFORE the price ceiling kicks in
    uncapped_purchases = 0
    if current_owned < cap_threshold:
        uncapped_purchases = min(num_purchased, cap_threshold - current_owned)
        total_cost += uncapped_purchases * base_price + increment_per_item * (
            uncapped_purchases * current_owned
            + (uncapped_purchases * (uncapped_purchases - 1)) // 2
        )

    # Units bought AFTER the ceiling (flat max price each)
    capped_purchases = num_purchased - uncapped_purchases
    if capped_purchases > 0:
        total_cost += capped_purchases * max_price

    return int(total_cost)
```
**Exact rule** (verbatim) - **Source:** `app_core/economy/building_costs.py:458-475`
```python
def land_city_purchase_cost(
    unit: str,
    current_owned: int,
    num_purchased: int,
    policies: list | None = None,
    price_multiplier: float = 1.0,
) -> int:
    """Gold cost of buying `num_purchased` land/cities in ONE province that
    already has `current_owned`. Single source of truth for both the
    single-province buy route and Mass Purchase, so a mass buy costs exactly
    what the same buys done province by province would."""
    base_price, increment, cap_threshold = LAND_CITY_PRICING[unit]
    if num_purchased <= 0:
        return 0
    raw = sum_cost_capped_linear(
        base_price, increment, int(current_owned or 0), int(num_purchased), cap_threshold
    )
    return int(apply_policy_gold_discount(unit, raw, policies) * price_multiplier)
```
**Units/range:** cities: base 750,000, +50,000 per owned city, ceiling after 200 owned (max price 750,000 + 200*50,000 = 10,750,000 each); land: base 520,000, +25,000 per owned land, ceiling after 100 owned (max 3,020,000 each). `land_drive` directive multiplies by 0.90.
**Used by (grep):** `land_city_purchase_cost` -> `province.py:1907`, `province.py:1960`, `province.py:2337`, `province.py:2344`, `province.py:2391`, `province.py:2731` (+2 more); `LAND_CITY_PRICING` -> `app_core/economy/building_costs.py:469`
**Notes:** the price is per PROVINCE (current_owned is that province's count). The gold discount (policy 2: x0.96) applies to land/city purchases too. Final amount is `int(discounted * price_multiplier)`.

Computed example (script output):
```
1st city in empty province (owned 0, buy 1): 750000
buy 10 cities, owned 0: 9750000
buy 1 city, owned 199: 10700000 ; owned 200: 10750000 ; owned 500: 10750000
buy 1 land, owned 0: 520000 ; owned 99: 2995000 ; owned 100: 3020000 ; owned 300: 3020000
buy 1 land owned 0 with policy 2: 499200 ; with land_drive 0.9: 468000
```

### Land/city sell price
**Exact rule** (verbatim) - **Source:** `province.py:1948-1958`
```python
            if units == "cityCount":
                raw_price = sum_cost_capped_linear(
                    750000, 50000, remaining, wantedUnits, cap_threshold=200
                )
            else:
                raw_price = sum_cost_capped_linear(
                    520000, 25000, remaining, wantedUnits, cap_threshold=100
                )
            from app_core.economy.building_costs import apply_policy_gold_discount
            discounted_price = apply_policy_gold_discount(units, raw_price, policies)
            totalPrice = max(0, int(discounted_price * SELL_REFUND_RATIO))
```
**Units/range:** refund = `int(discounted marginal price * 0.75)`. Cannot sell below 1 land/city, or below used slots (province.py:1936-1943 for the checks).

### New province price
**What it is:** price of the next province.
**Exact rule** (verbatim) - **Source:** `province.py:1346-1363`
```python
# Past this many provinces each new one costs PROVINCE_PRICE_GROWTH more on
# top of the linear price (2026-10-04 rebalance: 80 provinces in 3 days was
# far too easy). Existing provinces are never affected.
PROVINCE_PRICE_SOFT_LIMIT = 20
PROVINCE_PRICE_GROWTH = 1.08


def province_price_for_count(current_province_amount):
    """Price of the next province for a nation that owns this many."""
    if current_province_amount == 0:
        return 2000000
    if current_province_amount == 1:
        return 5000000
    price = 8000000 * (1 + (0.16 * current_province_amount))
    extra = current_province_amount - PROVINCE_PRICE_SOFT_LIMIT
    if extra > 0:
        price *= PROVINCE_PRICE_GROWTH**extra
    return int(price)
```
**Used by (grep):** `province_price_for_count` -> `province.py:1343`, `province.py:1353`; `get_province_price` -> `province.py:1337`, `province.py:1436`, `province.py:1734`, `province.py:1751`
**Units/range:** 0 owned: 2,000,000; 1 owned: 5,000,000; else `int(8,000,000 * (1 + 0.16*owned) * 1.08^max(0, owned-20))`.

Computed example (script output):
```
province_price_for_count(0) = 2000000
province_price_for_count(1) = 5000000
province_price_for_count(2) = 10560000
province_price_for_count(5) = 14400000
province_price_for_count(10) = 20800000
province_price_for_count(20) = 33600000
province_price_for_count(21) = 37670399
province_price_for_count(30) = 100174119
province_price_for_count(50) = 724511296
```

### Province rename cost
**Exact rule** (verbatim) - **Source:** `province.py:1366`
```python
PROVINCE_RENAME_COST = 10_000_000
```
### Directives (7-day timed boosts)
**What it is:** pay gold to get +5% tax or -10% land/city price for 7 days.
**Exact rule** (verbatim) - **Source:** `app_core/directives/services.py:9-22`
```python
DURATION_DAYS = 7

DIRECTIVES = {
    "tax_drive": {
        "name": "Tax Drive",
        "summary": "+5% tax income for 7 days.",
        "tax_multiplier": 1.05,
    },
    "land_drive": {
        "name": "Land Drive",
        "summary": "-10% price of land and cities for 7 days.",
        "land_multiplier": 0.90,
    },
}
```
**Exact rule** (verbatim) - **Source:** `app_core/directives/services.py:24-36`
```python
# Fee, in hours of the nation s own gross tax income. The Tax Drive pays back
# about 8.4 hours of income over its week, so the fee is below break-even but
# never free; it scales with the size of the nation.
COST_HOURS = 4
MIN_COST = 50_000


def tax_multiplier_for(active_keys):
    mult = 1.0
    for key in active_keys or ():
        mult *= DIRECTIVES.get(key, {}).get("tax_multiplier", 1.0)
    return mult

```
**Exact rule** (verbatim) - **Source:** `app_core/directives/services.py:76-77`
```python
    except (TypeError, ValueError):
        return set()
```
**Units/range:** fee = `max(50,000, hourly_income * 4)`; duration 7 days; cannot activate twice while active; fee is taken with `ledger.spend_gold` (services.py:107-111).
**Used by (grep):** `tax_multiplier_for` -> `countries.py:19`, `countries.py:550`, `app_core/directives/services.py:4`, `app_core/directives/services.py:31`, `app_core/game_ticks/taxes.py:56`, `app_core/game_ticks/taxes.py:115` (+1 more); `land_price_multiplier_for` -> `province.py:21`, `province.py:1965`, `province.py:2378`, `province.py:2738`, `app_core/directives/services.py:5`, `app_core/directives/services.py:38`

## Upkeep, output and effects per building (NEW_INFRA, the engine table)

### NEW_INFRA (what the tick reads)
**What it is:** per building per hour: gold upkeep (`money`), energy/resources produced (`plus`), resources consumed (`minus`), effect on province stats (`eff`/`effminus`).
**Exact rule** (verbatim) - **Source:** `variables.py:999-1229`
```python
NEW_INFRA = {  # (NEW INFRA)
    # ELECTRICITY
    "coal_burners": {
        "plus": {"energy": 4},
        "minus": {"coal": 11},
        "money": 7800,
        "eff": {"pollution": 6},
    },
    "oil_burners": {
        "plus": {"energy": 5},
        "minus": {"oil": 16},
        "money": 11700,
        "eff": {"pollution": 4},
    },
    "hydro_dams": {"plus": {"energy": 6}, "money": 24000},
    "nuclear_reactors": {
        "plus": {"energy": 15},
        "minus": {"uranium": 32},
        "money": 111000,
    },
    "solar_fields": {"plus": {"energy": 3}, "money": 13000},
    "wind_farms": {"plus": {"energy": 2}, "money": 8000},
    "geothermal_plants": {"plus": {"energy": 5}, "money": 20000},
    # RETAIL
    "food_banks": {
        "plus": {"consumer_goods": 2},
        "money": 2500,
    },
    "distribution_centers": {
        "plus": {"consumer_goods": 8},
        "money": 15000,
    },
    "gas_stations": {
        "plus": {"consumer_goods": 12},
        "eff": {"pollution": 4},
        "money": 20000,
    },
    "general_stores": {
        "plus": {"consumer_goods": 10},
        "eff": {"pollution": 2},
        "money": 37500,
    },
    "farmers_markets": {
        "plus": {"consumer_goods": 16},
        "eff": {"pollution": 5},
        "money": 48000,
    },
    "banks": {"plus": {"consumer_goods": 20}, "money": 100000},
    "malls": {
        "plus": {"consumer_goods": 30},
        "eff": {"pollution": 9},
        "money": 150000,
    },
    "industrial_district": {
        "plus": {"consumer_goods": 50},
        "eff": {"pollution": 15},
        "money": 85000,
    },
    "workshops": {
        "plus": {"consumer_goods": 4},
        "minus": {"steel": 2},
        "money": 12000,
        "eff": {"pollution": 1},
    },
    "jewelry_stores": {
        "plus": {"consumer_goods": 36},
        "minus": {"silver": 12, "diamonds": 6, "bullion": 8},
        "money": 60000,
        "eff": {"pollution": 2},
    },
    "automotive_plants": {
        "plus": {"consumer_goods": 160},
        "minus": {"steel": 40, "aluminium": 30, "components": 15},
        "money": 180000,
        "eff": {"pollution": 12},
    },
    # PUBLIC WORKS
    "city_parks": {
        "eff": {"happiness": 5},
        "effminus": {"pollution": 6},
        "money": 25000,
    },
    "libraries": {
        "eff": {"happiness": 5, "productivity": 3},
        "money": 60000,
    },
    "hospitals": {
        "eff": {"happiness": 8},
        "money": 85000,
    },
    "universities": {
        "eff": {"productivity": 10, "happiness": 4},
        "money": 175000,
    },
    "primary_school": {
        "eff": {"productivity": 2, "happiness": 2},
        "money": 30000,
    },
    "high_school": {
        "eff": {"productivity": 5, "happiness": 3},
        "money": 75000,
    },
    "monorails": {
        "eff": {"productivity": 16},
        "effminus": {"pollution": 20},
        "money": 270000,
    },
    "railways": {
        "eff": {"productivity": 8, "pollution": 2},
        "money": 67500,
    },
    "metros": {
        "eff": {"productivity": 12},
        "effminus": {"pollution": 10},
        "money": 150000,
    },
    "firewatch_towers": {
        "money": 1000,
    },
    "levees": {
        "money": 3000,
    },
    "seismic_reinforcements": {
        "money": 5000,
    },
    # MILITARY
    "army_bases": {"money": 25000},
    "harbours": {"money": 35000},
    "aerodomes": {"money": 55000},
    "admin_buildings": {"money": 90000},
    "silos": {"money": 340000},
    # Unit production (kamikaze_drones/cruise_missiles) happens in the
    # separate app_core/game_ticks/unit_production.py tick, not here — this
    # entry only covers the building's gold upkeep, same as every other
    # military building above.
    "drone_sites": {"money": 5000},
    "missile_batteries": {"money": 40000},
    # INDUSTRY
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
    "pumpjacks": {"money": 9500, "plus": {"oil": 100}, "eff": {"pollution": 2}},
    "coal_mines": {
        "money": 4200,  # Costs $10k
        "plus": {"coal": 120},
        "eff": {"pollution": 2},
    },
    "bauxite_mines": {
        "money": 8000,  # Costs $8k
        "plus": {"bauxite": 260},
        "eff": {"pollution": 2},
    },
    "copper_mines": {
        "money": 5000,
        "plus": {"copper": 120},
        "eff": {"pollution": 2},
    },
    "uranium_mines": {
        "money": 45000,  # Costs $18k
        "plus": {"uranium": 40},
        "eff": {"pollution": 1},
    },
    "lead_mines": {
        "money": 7200,
        "plus": {"lead": 80},
        "eff": {"pollution": 2},
    },
    "iron_mines": {
        "money": 11000,
        "plus": {"iron": 70},
        "eff": {"pollution": 2},
    },
    "lumber_mills": {
        "money": 7500,
        "plus": {"lumber": 150},
        "eff": {"pollution": 1},
    },
    "silver_mines": {
        "money": 12000,
        "plus": {"silver": 60},
        "eff": {"pollution": 2},
    },
    "diamond_mines": {
        "money": 25000,
        "plus": {"diamonds": 30},
        "eff": {"pollution": 2},
    },
    "bullion_mines": {
        "money": 18000,
        "plus": {"bullion": 40},
        "eff": {"pollution": 2},
    },
    # PROCESSING
    "component_factories": {
        "money": 50000,  # Costs $220k
        "minus": {"copper": 80, "steel": 40, "aluminium": 60},
        "plus": {"components": 20},
        "eff": {"pollution": 5},
    },
    "steel_mills": {
        "money": 60000,
        "minus": {"coal": 38, "iron": 67},
        "plus": {"steel": 48},
        "eff": {"pollution": 4},
    },
    "ammunition_factories": {
        "money": 15000,
        "minus": {"copper": 40, "lead": 80},
        "plus": {"ammunition": 48},
        "eff": {"pollution": 3},
    },
    "aluminium_refineries": {
        "money": 42000,
        "minus": {"bauxite": 256},
        "plus": {"aluminium": 64},
        "eff": {"pollution": 3},
    },
    "oil_refineries": {
        "money": 35000,
        "minus": {"oil": 88},
        "plus": {"gasoline": 44},
        "eff": {"pollution": 6},
    },
}
```
**Units/range:** all per ONE building per hour, before upgrades/policies/multipliers (see economy-taxes-revenue.md).
**Used by (grep):** `NEW_INFRA` -> `ai_agent.py:492`, `ai_agent.py:529`, `ai_agent.py:539`, `influence_formula.py:24`, `influence_formula.py:109`, `influence_formula.py:118` (+14 more)
**Notes:** the display table `INFRA` (variables.py:572-738) holds the same numbers under flattened keys; a script comparison found no differences (see below). `building_info` and `building_description` (app_core/economy/building_costs.py:206-250, 289-400) generate the text players see from NEW_INFRA, so those texts follow the code.

### Gold upkeep list, categories and order
**Exact rule** (verbatim) - **Source:** `variables.py:433-509`
```python
INFRA_TYPES = [
    "electricity",
    "retail",
    "public_works",
    "military",
    "industry",
    "processing",
]
INFRA_TYPE_BUILDINGS = {
    "electricity": [
        "coal_burners",
        "oil_burners",
        "hydro_dams",
        "nuclear_reactors",
        "solar_fields",
        "wind_farms",
        "geothermal_plants",
    ],
    "retail": [
        "gas_stations",
        "general_stores",
        "farmers_markets",
        "malls",
        "banks",
        "food_banks",
        "distribution_centers",
        "industrial_district",
        "workshops",
        "jewelry_stores",
        "automotive_plants",
    ],
    "public_works": [
        "hospitals",
        "libraries",
        "universities",
        "primary_school",
        "high_school",
        "city_parks",
        "monorails",
        "railways",
        "metros",
        "firewatch_towers",
        "levees",
        "seismic_reinforcements",
    ],
    "military": [
        "army_bases",
        "harbours",
        "aerodomes",
        "admin_buildings",
        "silos",
        "drone_sites",
        "missile_batteries",
    ],
    "industry": [
        "farms",
        "pumpjacks",
        "coal_mines",
        "bauxite_mines",
        "copper_mines",
        "uranium_mines",
        "lead_mines",
        "iron_mines",
        "lumber_mills",
        "silver_mines",
        "diamond_mines",
        "bullion_mines",
        "fisheries",
    ],
    "processing": [
        "component_factories",
        "steel_mills",
        "ammunition_factories",
        "aluminium_refineries",
        "oil_refineries",
    ],
}
```
**Exact rule** (verbatim) - **Source:** `variables.py:511-567`
```python
BUILDINGS = [
    "coal_burners",
    "oil_burners",
    "hydro_dams",
    "nuclear_reactors",
    "solar_fields",
    "wind_farms",
    "geothermal_plants",
    "gas_stations",
    "general_stores",
    "farmers_markets",
    "malls",
    "banks",
    "industrial_district",
    "hospitals",
    "libraries",
    "universities",
    "primary_school",
    "high_school",
    "farms",
    "pumpjacks",
    "coal_mines",
    "bauxite_mines",
    "copper_mines",
    "uranium_mines",
    "lead_mines",
    "iron_mines",
    "lumber_mills",
    "silver_mines",
    "diamond_mines",
    "bullion_mines",
    "fisheries",
    "component_factories",
    "steel_mills",
    "ammunition_factories",
    "aluminium_refineries",
    "oil_refineries",
    "food_banks",
    "distribution_centers",
    "workshops",
    "jewelry_stores",
    "automotive_plants",
    "army_bases",
    "harbours",
    "aerodomes",
    "admin_buildings",
    "silos",
    "drone_sites",
    "missile_batteries",
    "city_parks",
    "monorails",
    "railways",
    "metros",
    "firewatch_towers",
    "levees",
    "seismic_reinforcements",  # Had to put them here so pollution would be minused at the end
]
```
**Notes:** `variables.BUILDINGS` ORDER is the processing order in the revenue tick (power plants first) and the comment at variables.py:566 says seismic_reinforcements is last so pollution is reduced at the end. `UPGRADES = {"oil_burners"}` (variables.py:569) is a leftover set; see grep:
**Used by (grep):** `UPGRADES` -> `templates/upgrades_v2.html:22`

### Employment matrix (jobs per building)
**Exact rule** (verbatim) - **Source:** `variables.py:244-301`
```python
BUILDING_EMPLOYMENT_MATRICES = {
    "farms": {"worker_count": 50000, "education": {"edu_none": 1.0}},
    "coal_burners": {
        "worker_count": 80000,
        "education": {"edu_highschool": 0.4, "edu_college": 0.6},
    },
    "oil_burners": {
        "worker_count": 75000,
        "education": {"edu_highschool": 0.4, "edu_college": 0.6},
    },
    "nuclear_reactors": {
        "worker_count": 150000,
        "education": {"edu_highschool": 0.4, "edu_college": 0.6},
    },
    "hydro_dams": {
        "worker_count": 120000,
        "education": {"edu_highschool": 0.4, "edu_college": 0.6},
    },
    "solar_fields": {
        "worker_count": 60000,
        "education": {"edu_highschool": 0.3, "edu_college": 0.7},
    },
    "wind_farms": {
        "worker_count": 40000,
        "education": {"edu_highschool": 0.5, "edu_college": 0.5},
    },
    "geothermal_plants": {
        "worker_count": 80000,
        "education": {"edu_highschool": 0.2, "edu_college": 0.8},
    },
    "industrial_district": {
        "worker_count": 200000,
        "education": {"edu_none": 0.8, "edu_highschool": 0.2},
    },
    "primary_school": {
        "worker_count": 30000,
        "education": {"edu_none": 1.0},
    },
    "high_school": {
        "worker_count": 40000,
        "education": {"edu_none": 1.0},
    },
    "universities": {
        "worker_count": 50000,
        "education": {
            "edu_highschool": 0.8,
            "edu_college": 0.2,
        },
    },
    "component_factories": {
        "worker_count": 100000,
        "education": {"edu_highschool": 0.4, "edu_college": 0.6},
    },
    "steel_mills": {
        "worker_count": 90000,
        "education": {"edu_none": 0.6, "edu_highschool": 0.4},
    },
}
```
**Units/range:** workers per building and education mix. Only buildings listed here need workers (see consistency checks).
**Used by (grep):** `BUILDING_EMPLOYMENT_MATRICES` -> `countries.py:331`, `province.py:2721`, `services/country_service.py:396`, `app_core/game_ticks/population.py:891`, `app_core/game_ticks/population.py:955`, `app_core/game_ticks/revenue.py:458` (+5 more)

### Consistency checks (script output)
```
INFRA vs NEW_INFRA differences: none
BUILDINGS without NEW_INFRA entry: []
BUILDINGS without PROVINCE_UNIT_PRICES price: []
BUILDINGS without PROVINCE_UNIT_PRICES resource: ['lumber_mills']
BUILDINGS without BUILDING_EMPLOYMENT_MATRICES entry (employ no workers): ['gas_stations', 'general_stores', 'farmers_markets', 'malls', 'banks', 'hospitals', 'libraries', 'pumpjacks', 'coal_mines', 'bauxite_mines', 'copper_mines', 'uranium_mines', 'lead_mines', 'iron_mines', 'lumber_mills', 'silver_mines', 'diamond_mines', 'bullion_mines', 'fisheries', 'ammunition_factories', 'aluminium_refineries', 'oil_refineries', 'food_banks', 'distribution_centers', 'workshops', 'jewelry_stores', 'automotive_plants', 'army_bases', 'harbours', 'aerodomes', 'admin_buildings', 'silos', 'drone_sites', 'missile_batteries', 'city_parks', 'monorails', 'railways', 'metros', 'firewatch_towers', 'levees', 'seismic_reinforcements']
BUILDINGS not in any INFRA_TYPE_BUILDINGS category: []
category members not in BUILDINGS: []
ENERGY_CONSUMERS not in BUILDINGS: []
BUILDING_EMPLOYMENT_MATRICES keys not in BUILDINGS: []
education shares all sum to 1.0 otherwise
Order check: index of last power plant in BUILDINGS = 6 ; first ENERGY_CONSUMERS building index = 7
```

## Not found / open questions
- Whether `building_dictionary` rows (DB) carry other prices that some code path still reads (the `enrich_building_row` function overrides `gold_cost` from variables, app_core/economy/building_costs.py:403-420).
- Whether `/build_structure` with negative quantity blocks selling during war (see UNCLEAR above).
- Build time/queue: none found; `build_structure` completes instantly in one transaction (action_loop.py:48-96).
