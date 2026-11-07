# Energy (electricity)

Energy is a per-PROVINCE stat reset every hour and rebuilt by that province's own power plants during the revenue tick (:25). It is not stored between ticks and not shared between provinces.

## Order of operations
1. For each province: `energy = 0` (app_core/game_ticks/revenue.py:392-393).
2. Buildings processed in `variables.BUILDINGS` order; the 7 power plants are the first 7 entries (variables.py:512-518), so every energy consumer (`variables.ENERGY_CONSUMERS`) comes later. Verified by script (see below).
3. Each consumer's affordable units are limited by `energy // energy_per_unit` (revenue.py:774-786).
4. Power plants themselves need gold and (coal/oil/uranium) input resources (revenue.py:830-838) and are processed through the same partial-operation logic.

## Entries

### Power plant output, fuel and upkeep
**What it is:** electricity produced per building per hour, with fuel input and gold upkeep.
**Exact rule** (verbatim) - **Source:** `variables.py:1001-1021`
```python
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
```
**Units/range:** energy units per building per hour (before productivity/other multipliers: `plus_amount_multiplier` applies to energy too, because energy is a `plus` resource, revenue.py:970-981).
**Used by (grep):** `ENERGY_UNITS` -> `app_core/game_ticks/energy.py:61`, `app_core/economy/province_power.py:23`, `app_core/economy/province_energy.py:78`, `app_core/economy/province_energy.py:86`
**Notes:** the output `amount = ceil(base * affordable_units * plus_amount_multiplier)` includes the productivity multiplier (revenue.py:981). Province energy is not clamped by `percentage_based`.

### Energy consumers
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
**Units/range:** 1 energy per building per hour; steel mills 2 with the Electric Arc Furnace upgrade.
**Notes:** power plants themselves are not in `ENERGY_CONSUMERS`. Military buildings, mines, farms and fisheries are not either (variables.py:406-429): they need no electricity.

### Better Engineering (nuclear)
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/revenue.py:908-910`
```python
                        # BETTER ENGINEERING
                        if unit == "nuclear_reactors" and upgrades.get("betterengineering"):
                            plus["energy"] += 6
```
**Units/range:** +6 energy per nuclear reactor before multipliers (15 -> 21 base).

### Idle consequence
**What it is:** if a province lacks energy, consumers stop for that province only.
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/revenue.py:783-786`
```python
                            affordable_by_energy = int(current_energy // energy_per_unit)
                            if affordable_by_energy < affordable_units:
                                has_enough_stuff["issues"].append("energy")
                            affordable_units = min(affordable_units, affordable_by_energy)
```
**Notes:** buildings that cannot run produce nothing, pay no upkeep, and apply no happiness/pollution effects (revenue.py:840-846 `continue`). A province page projection of the same logic lives in app_core/economy/province_energy.py.

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
- Whether the nation-level power view (app_core/economy/province_power.py) uses different rounding than the tick (only the tick's lines are cited here).
- No "no-energy" tax penalty was found in code; `NO_ENERGY_TAX_MULTIPLIER` is unused (see economy-taxes-revenue.md).
