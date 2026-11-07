# Resources and production

Production happens in the hourly `generate_province_revenue` tick (:25). The exact formula (productivity, project bonuses, specialisation, vertical integration, workforce) is in economy-taxes-revenue.md "Output formula".

## Resource list

### Resources that exist
**What it is:** the resource names the game knows.
**Exact rule** (verbatim) - **Source:** `variables.py:375-394`
```python
RESOURCES = [
    "rations",
    "oil",
    "coal",
    "uranium",
    "bauxite",
    "lead",
    "copper",
    "iron",
    "lumber",
    "silver",
    "diamonds",
    "bullion",
    "components",
    "steel",
    "consumer_goods",
    "aluminium",
    "gasoline",
    "ammunition",
]
```
**Used by (grep):** `RESOURCES` -> `countries.py:243`, `templates/mechanics.html:186`, `templates/province.html:1871`, `templates/admin_command_center.html:86`, `services/country_service.py:117`, `app_core/trade_agreements/repositories.py:7` (+19 more)
**Notes:** `variables.RESOURCES` has 18 names (includes silver, diamonds, bullion); `Economy.resources` used for war transfers has 15 (no silver/diamonds/bullion), see economy-taxes-revenue.md.

### Raw producers (industry buildings): output per building per hour
**What it is:** base output of mines, farms, etc. with their gold upkeep and pollution.
**Exact rule** (verbatim) - **Source:** `variables.py:1137-1197`
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
```
**Units/range:** `plus` = resource units per building per hour at productivity 50, base `money` = gold per hour.

### Processing buildings (inputs -> outputs)
**Exact rule** (verbatim) - **Source:** `variables.py:1198-1229`
```python
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
**Notes:** a processing building consumes `minus` per building per hour; it produces nothing unless every input can be paid for at least one building (see partial operation in economy-taxes-revenue.md).

### Power plants
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
**Notes:** see energy.md.

### Retail buildings (consumer goods)
**Exact rule** (verbatim) - **Source:** `variables.py:1023-1074`
```python
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
```
**Units/range:** `plus consumer_goods` is units of consumer goods PRODUCED per building per hour into the nation's stockpile (they are consumed by the tax tick; capacity to DELIVER is a separate table, see economy-taxes-revenue.md).

### Unit stockpile production (drone sites, missile batteries)
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
**Notes:** see military-units.md.

### Bonuses that change output
- Productivity (province stat): economy-taxes-revenue.md "Productivity output multiplier".
- Economies of scale / vertical integration: economy-taxes-revenue.md.
- National projects (upgrades): `PROJECT_OUTPUT_BONUSES` bauxite_mines +45% (strongerexplosives), farms +50% (advancedmachinery), steel_mills +36% (integratedsteelmaking); source app_core/economy/project_bonuses.py:23-27.
- Workforce efficiency: floor 20%.

### Biome (location) effects
**What it is:** the nation's biome (`stats.location`) restricts or modifies buildings.
**Exact rule** (verbatim) - **Source:** `app_core/economy/biome_buildings.py:36-44`
```python
BIOME_MINES: dict[str, tuple[str, ...]] = {
    "tundra": ("iron_mines", "copper_mines", "lead_mines", "uranium_mines", "silver_mines"),
    "desert": ("iron_mines", "pumpjacks", "bauxite_mines", "uranium_mines", "diamond_mines"),
    "boreal forest": ("iron_mines", "lumber_mills", "lead_mines", "coal_mines", "bullion_mines"),
    "grassland": ("iron_mines", "copper_mines", "bauxite_mines", "pumpjacks"),
    "savanna": ("coal_mines", "copper_mines", "lead_mines", "bauxite_mines", "diamond_mines"),
    "mountain range": ("coal_mines", "pumpjacks", "bauxite_mines", "lumber_mills", "silver_mines"),
    "jungle": ("coal_mines", "copper_mines", "lumber_mills", "pumpjacks", "bullion_mines"),
}
```
**Exact rule** (verbatim) - **Source:** `app_core/economy/biome_buildings.py:120-136`
```python

def mines_for_biome(location: str | None) -> tuple[str, ...]:
    """Raw-material mine/well types buildable in a given province biome.

    Falls back to the full list for unrecognized location values (a
    handful of legacy accounts carry stale/corrupt `stats.location` data)
    rather than silently blocking every mine purchase for those accounts.
    """
    if not location:
        return ALL_MINE_BUILDINGS
    return BIOME_MINES.get(location.strip().lower(), ALL_MINE_BUILDINGS)


def is_mine_allowed_in_biome(building_name: str, location: str | None) -> bool:
    if building_name not in ALL_MINE_BUILDINGS:
        return True  # not a biome-restricted building type
    return building_name in mines_for_biome(location)
```
**Used by (grep):** `is_mine_allowed_in_biome` -> `app_core/economy/biome_buildings.py:133`, `app_core/economy/building_purchase.py:7`, `app_core/economy/building_purchase.py:113`; `mines_for_biome` -> `province.py:41`, `province.py:1075`, `game_ui.py:488`, `game_ui.py:492`, `app_core/economy/biome_buildings.py:113`, `app_core/economy/biome_buildings.py:121` (+4 more)
**Notes:** unknown/empty biome allows ALL mines. Farms, fisheries, factories etc. are not biome restricted here. Server-side purchase validation calls `is_mine_allowed_in_biome` at app_core/economy/building_purchase.py:113.

## Not found / open questions
- Resource stockpile caps (no cap found in the tick; `large_storehouses` tech exists in the upgrade name map but no code reads it - see tech-upgrades-policies.md).
- Biome effects on production other than the mine availability and pollution decay in vegetated biomes.
