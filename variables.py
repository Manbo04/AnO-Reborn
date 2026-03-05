# File for variables that are repeated multiple times in other files
# (for example, the resources list)

DEFAULT_TAX_INCOME = 0.50
CONSUMER_GOODS_TAX_MULTIPLIER = 1.5
NO_ENERGY_TAX_MULTIPLIER = (
    0.85  # How much the tax income will decrease if there's no energy -15%
)
NO_FOOD_TAX_MULTIPLIER = (
    0.7  # How much the tax income will decrease if there's no food -30%
)
DEFAULT_LAND_TAX_MULTIPLIER = 0.02  # Multiplier of tax income per land slot
# Population growth multipliers - now more realistic
# Higher happiness increases growth, pollution decreases it
DEFAULT_HAPPINESS_GROWTH_MULTIPLIER = 0.04  # 4% impact per happiness point
DEFAULT_POLLUTION_GROWTH_MULTIPLIER = 0.02  # 2% impact per pollution point

DEFAULT_MAX_POPULATION = 1000000
CITY_MAX_POPULATION_ADDITION = 750000
LAND_MAX_POPULATION_ADDITION = 120000

DEFAULT_PRODUCTIVITY_PRODUCTION_MUTLIPLIER = 0.009  # 9%

LAND_FARM_PRODUCTION_ADDITION = 3

CONSUMER_GOODS_PER = 80000  # 1 Consumer good per x population
RATIONS_PER = 50000  # 1 Ration per x population (lower = more rations needed)

# Building-based distribution requirement for rations.  Each province must
# not only have farms producing food but also enough retail/distribution
# buildings to move the food around; otherwise the population effectively
# has no rations even if the resource number is high.
# NOTE: enabled by default following 2026‑02‑24 deployment.
FEATURE_RATIONS_DISTRIBUTION = True  # toggle the new mechanic on/off
RATIONS_DISTRIBUTION_BUILDINGS = [
    "gas_stations",
    "general_stores",
    "farmers_markets",
    "malls",
]
RATIONS_DISTRIBUTION_PER_BUILDING = 50000  # population served per building

# DEMOGRAPHIC-BASED CONSUMPTION (Phase 2)
# Each demographic bracket has different consumption rates for rations and CG
# Base units: consumption per person per tick
DEMO_RATIONS_CONSUMPTION = {
    "pop_working": 1.0,  # 1 ration per working-age person per tick
    "pop_children": 1.3,  # 30% higher rations due to nutritional needs
    "pop_elderly": 0.8,  # Slightly lower than working
}
DEMO_CONSUMER_GOODS_CONSUMPTION = {
    "pop_working": 1.0,  # 1 CG per working-age person per tick
    "pop_children": 1.2,  # High CG consumption (toys, education materials)
    "pop_elderly": 2.0,  # 2x CG consumption (healthcare, comfort goods)
}

# Distribution capacity for different building types
# These cap how much rations/CG can actually be consumed even if available
CONSUMER_GOODS_DISTRIBUTION_BUILDINGS = [
    "malls",
    "general_stores",
    "gas_stations",
]
CONSUMER_GOODS_DISTRIBUTION_PER_BUILDING = 50000  # population served per building

# Feature flag for demographic-based consumption system
FEATURE_DEMOGRAPHIC_CONSUMPTION = True  # toggle the new mechanic on/off

# PHASE 3: AGING, EDUCATION & WORKFORCE (Phase 3)
# Daily population aging rates (per tick, as fraction)
DEMO_AGING_RATES = {
    "elderly_death_rate": 0.002,  # 0.2% of elderly die per tick
    "working_to_elderly_rate": 0.001,  # 0.1% move to elderly per tick
    "children_to_working_rate": 0.005,  # 0.5% graduate to working per tick
}

# Education distribution (when children graduate)
# Determined by available school/university capacity in province
EDUCATION_GRADUATION_PRIORITY = [
    "university",  # If capacity available -> edu_college
    "high_school",  # Else if capacity available -> edu_highschool
    # Else -> edu_none (default)
]

# Building employment matrices
# Format: building_name -> {worker_count: int, education_requirements: {edu_level: %}}
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
    "university": {
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

# Feature flag for Phase 3 (workforce/employment system)
FEATURE_PHASE3_WORKFORCE = True

# HOTFIX: disable military desertion mechanic until Economy 2.0 gasoline math
# is confirmed stable. Set to True only after verifying oil refinery production
# is correctly flowing and player stockpiles have recovered.
FEATURE_MILITARY_DESERTION = False

# Debuff thresholds
UNEMPLOYMENT_THRESHOLD = 0.3  # 30%+ unemployment triggers debuff
UNEMPLOYMENT_HAPPINESS_PENALTY = 10  # Happiness loss per tick
PENSION_CRISIS_RATIO = 0.4  # Elderly > 40% of working = pension crisis
PENSION_CRISIS_GOLD_PENALTY = 5000  # Gold cost per tick when in crisis
PRODUCTION_EFFICIENCY_MIN = 0.2  # Minimum 20% production if severely understaffed

# POLICY DEFINITIONS
# Policy IDs (stored as integers in user's policy arrays)
POLICY_UNIVERSAL_HEALTHCARE = 1
POLICY_MANDATORY_SCHOOLING = 2
POLICY_INDUSTRIAL_SUBSIDIES = 3
POLICY_RATIONING_PROGRAM = 4

# Policy effect multipliers
POLICY_HEALTHCARE_ELDERLY_CG_MULTIPLIER = 1.2  # +20% elderly CG consumption
POLICY_HEALTHCARE_ELDERLY_DEATH_REDUCTION = 0.7  # -30% elderly death rate
POLICY_HEALTHCARE_HAPPINESS_BONUS = 5  # +5 happiness per province

POLICY_SCHOOLING_GRADUATION_MULTIPLIER = 1.5  # +50% graduation rates
POLICY_SCHOOLING_HAPPINESS_BONUS = 3  # +3 happiness (educated populace)

POLICY_SUBSIDIES_UPKEEP_REDUCTION = 0.7  # -30% upkeep for industrial buildings
POLICY_SUBSIDIES_POLLUTION_MULTIPLIER = 1.3  # +30% pollution from industry
POLICY_SUBSIDIES_AFFECTED_BUILDINGS = [
    "industrial_district",
    "component_factories",
    "steel_mills",
    "coal_burners",
    "oil_burners",
]

POLICY_RATIONING_CONSUMPTION_REDUCTION = 0.85  # -15% rations consumption
POLICY_RATIONING_HAPPINESS_PENALTY = 10  # -10 happiness per province

UNITS = [
    "soldiers",
    "tanks",
    "artillery",
    "bombers",
    "fighters",
    "apaches",
    "destroyers",
    "cruisers",
    "submarines",
    "spies",
    "icbms",
    "nukes",
]
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
    "components",
    "steel",
    "consumer_goods",
    "aluminium",
    "gasoline",
    "ammunition",
]

ENERGY_UNITS = [
    "coal_burners",
    "oil_burners",
    "hydro_dams",
    "nuclear_reactors",
    "solar_fields",
]

ENERGY_CONSUMERS = [
    "gas_stations",
    "general_stores",
    "farmers_markets",
    "malls",
    "banks",
    "city_parks",
    "hospitals",
    "libraries",
    "universities",
    "monorails",
    "component_factories",
    "steel_mills",
    "ammunition_factories",
    "aluminium_refineries",
    "oil_refineries",
]

TRADE_TYPES = ["buy", "sell"]

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
    ],
    "retail": ["gas_stations", "general_stores", "farmers_markets", "malls", "banks"],
    "public_works": [
        "hospitals",
        "libraries",
        "universities",
        "city_parks",
        "monorails",
    ],
    "military": ["army_bases", "harbours", "aerodomes", "admin_buildings", "silos"],
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
    ],
    "processing": [
        "component_factories",
        "steel_mills",
        "ammunition_factories",
        "aluminium_refineries",
        "oil_refineries",
    ],
}

BUILDINGS = [
    "coal_burners",
    "oil_burners",
    "hydro_dams",
    "nuclear_reactors",
    "solar_fields",
    "gas_stations",
    "general_stores",
    "farmers_markets",
    "malls",
    "banks",
    "hospitals",
    "libraries",
    "universities",
    "farms",
    "pumpjacks",
    "coal_mines",
    "bauxite_mines",
    "copper_mines",
    "uranium_mines",
    "lead_mines",
    "iron_mines",
    "lumber_mills",
    "component_factories",
    "steel_mills",
    "ammunition_factories",
    "aluminium_refineries",
    "oil_refineries",
    "city_parks",
    "monorails",  # Had to put them here so pollution would be minused at the end
]

UPGRADES = {"oil_burners"}

# Dictionary for which units give what resources, etc ()
INFRA = {  # (OLD INFRA)
    # Electricity (done)
    "coal_burners_plus": {"energy": 4},  # Energy increase
    "coal_burners_convert_minus": [{"coal": 11}],  # Resource upkeep cost
    "coal_burners_money": 7800,  # Monetary upkeep cost
    "coal_burners_effect": [{"pollution": 6}],  # Pollution amount added
    "oil_burners_plus": {"energy": 5},
    "oil_burners_convert_minus": [{"oil": 16}],
    "oil_burners_money": 11700,
    "oil_burners_effect": [{"pollution": 4}],
    "hydro_dams_plus": {"energy": 6},
    "hydro_dams_money": 24000,
    "nuclear_reactors_plus": {"energy": 15},
    "nuclear_reactors_convert_minus": [{"uranium": 32}],
    "nuclear_reactors_money": 111000,
    "solar_fields_plus": {"energy": 3},
    "solar_fields_money": 11000,
    ####################
    # Retail (Done)
    "gas_stations_plus": {"consumer_goods": 50000},
    "gas_stations_effect": [{"pollution": 4}],
    "gas_stations_money": 20000,
    "general_stores_plus": {"consumer_goods": 40000},
    "general_stores_effect": [{"pollution": 2}],
    "general_stores_money": 37500,
    "farmers_markets_plus": {"consumer_goods": 60000},
    "farmers_markets_effect": [{"pollution": 5}],
    "farmers_markets_money": 80000,
    "banks_plus": {"consumer_goods": 80000},
    "banks_money": 220000,
    "malls_plus": {"consumer_goods": 100000},
    "malls_effect": [{"pollution": 9}],
    "malls_money": 450000,  # Costs $750k
    "industrial_district_plus": {"consumer_goods": 300000},
    "industrial_district_effect": [{"pollution": 15}],
    "industrial_district_money": 85000,
    ##############
    # Public Works (Done)
    "city_parks_effect": [{"happiness": 5}],
    "city_parks_effect_minus": {"pollution": 6},
    "city_parks_money": 25000,
    "libraries_effect": [{"happiness": 5}, {"productivity": 3}],
    "libraries_money": 60000,
    "hospitals_effect": [{"happiness": 8}],
    "hospitals_money": 85000,
    "universities_effect": [{"productivity": 10}, {"happiness": 4}],
    "universities_money": 175000,
    "monorails_effect": [{"productivity": 16}],
    "monorails_effect_minus": {"pollution": 20},
    "monorails_money": 270000,
    ###################
    # Military (Done)
    "army_bases_money": 25000,  # Costs $25k
    "harbours_money": 35000,
    "aerodomes_money": 55000,
    "admin_buildings_money": 90000,
    "silos_money": 340000,
    ################
    # Industry (Done) - Now in kg (weight-based)
    "farms_money": 5000,
    "farms_plus": {"rations": 150000},
    "farms_effect": [{"pollution": 1}],
    "pumpjacks_money": 5000,
    "pumpjacks_plus": {"oil": 100000},
    "pumpjacks_effect": [{"pollution": 2}],
    "coal_mines_money": 5000,
    "coal_mines_plus": {"coal": 90000},
    "coal_mines_effect": [{"pollution": 2}],
    "bauxite_mines_money": 5000,
    "bauxite_mines_plus": {"bauxite": 80000},
    "bauxite_mines_effect": [{"pollution": 2}],
    "copper_mines_money": 5000,
    "copper_mines_plus": {"copper": 70000},
    "copper_mines_effect": [{"pollution": 2}],
    "uranium_mines_money": 45000,
    "uranium_mines_plus": {"uranium": 60000},
    "uranium_mines_effect": [{"pollution": 1}],
    "lead_mines_money": 5000,
    "lead_mines_plus": {"lead": 65000},
    "lead_mines_effect": [{"pollution": 2}],
    "iron_mines_money": 5000,
    "iron_mines_plus": {"iron": 80000},
    "iron_mines_effect": [{"pollution": 2}],
    "lumber_mills_money": 5000,
    "lumber_mills_plus": {"lumber": 100000},
    "lumber_mills_effect": [{"pollution": 1}],
    ################
    # Processing (Done) - Now in kg (weight-based)
    "component_factories_money": 50000,
    "component_factories_convert_minus": [
        {"copper": 20000},
        {"steel": 10000},
        {"aluminium": 15000},
    ],
    "component_factories_plus": {"components": 40000},
    "component_factories_effect": [{"pollution": 5}],
    "steel_mills_money": 60000,
    "steel_mills_convert_minus": [{"coal": 35000}, {"iron": 35000}],
    "steel_mills_plus": {"steel": 50000},
    "steel_mills_effect": [{"pollution": 4}],
    "ammunition_factories_money": 15000,
    "ammunition_factories_convert_minus": [{"copper": 10000}, {"lead": 20000}],
    "ammunition_factories_plus": {"ammunition": 55000},
    "ammunition_factories_effect": [{"pollution": 3}],
    "aluminium_refineries_money": 42000,
    "aluminium_refineries_convert_minus": [{"bauxite": 15000}],
    "aluminium_refineries_plus": {"aluminium": 60000},
    "aluminium_refineries_effect": [{"pollution": 3}],
    "oil_refineries_money": 35000,
    "oil_refineries_convert_minus": [{"oil": 20000}],
    "oil_refineries_plus": {"gasoline": 75000},
    "oil_refineries_effect": [{"pollution": 6}],
}

MILDICT = {
    # LAND
    "soldiers": {"price": 200, "resources": {"rations": 2}, "manpower": 1},
    "tanks": {"price": 8000, "resources": {"steel": 5, "components": 5}, "manpower": 4},
    "artillery": {
        "price": 16000,
        "resources": {"steel": 12, "components": 3},
        "manpower": 2,
    },
    # AIR
    "bombers": {
        "price": 25000,
        "resources": {"aluminium": 20, "steel": 5, "components": 6},
        "manpower": 1,
    },
    "fighters": {
        "price": 35000,
        "resources": {"aluminium": 12, "components": 3},
        "manpower": 1,
    },
    "apaches": {
        "price": 32000,
        "resources": {"aluminium": 8, "steel": 2, "components": 4},
        "manpower": 1,
    },
    # WATER
    "destroyers": {
        "price": 30000,
        "resources": {"steel": 30, "components": 7},
        "manpower": 6,
    },
    "cruisers": {
        "price": 55000,
        "resources": {"steel": 60, "components": 12},
        "manpower": 5,
    },
    "submarines": {
        "price": 45000,
        "resources": {"steel": 20, "components": 8},
        "manpower": 6,
    },
    # SPECIAL
    "spies": {
        "price": 25000,  # Cost 25k
        "resources": {"rations": 50},  # Costs 50 rations
        "manpower": 0,
    },
    "icbms": {
        "price": 16000000,  # Cost 16 million
        "resources": {"steel": 550},
        "manpower": 0,
    },
    "nukes": {
        "price": 80000000,
        "resources": {"uranium": 1200, "steel": 900},
        "manpower": 0,
    },
}

PROVINCE_UNIT_PRICES = {
    "land_price": 0,
    "cityCount_price": 0,
    # Power Generation (Tier 2-3)
    "coal_burners_price": 2500000,
    "coal_burners_resource": {"aluminium": 60000},
    "oil_burners_price": 4500000,
    "oil_burners_resource": {"aluminium": 75000},
    "hydro_dams_price": 35000000,
    "hydro_dams_resource": {"steel": 180000, "aluminium": 90000},
    "nuclear_reactors_price": 150000000,
    "nuclear_reactors_resource": {"steel": 500000},
    "solar_fields_price": 8000000,
    "solar_fields_resource": {"steel": 85000},
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
    # Public Works (Tier 2-3)
    "city_parks_price": 4500000,
    "city_parks_resource": {"steel": 22000},
    "hospitals_price": 30000000,
    "hospitals_resource": {"steel": 210000, "aluminium": 130000},
    "libraries_price": 10000000,
    "libraries_resource": {"steel": 85000, "aluminium": 60000},
    "universities_price": 95000000,
    "universities_resource": {"steel": 320000, "aluminium": 160000},
    "monorails_price": 250000000,
    "monorails_resource": {"steel": 600000, "aluminium": 300000},
    # Education Buildings (Tier 2)
    "primary_school_price": 8000000,
    "primary_school_resource": {"steel": 50000, "aluminium": 30000},
    "high_school_price": 25000000,
    "high_school_resource": {"steel": 120000, "aluminium": 80000},
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
    # Resource Extraction (Tier 1)
    "farms_price": 1500000,
    "farms_resource": {"lumber": 15000},
    "pumpjacks_price": 3000000,
    "pumpjacks_resource": {"steel": 22000},
    "coal_mines_price": 3500000,
    "coal_mines_resource": {"lumber": 45000},
    "bauxite_mines_price": 3200000,
    "bauxite_mines_resource": {"lumber": 30000},
    "copper_mines_price": 2800000,
    "copper_mines_resource": {"lumber": 38000},
    "uranium_mines_price": 5500000,
    "uranium_mines_resource": {"steel": 52000},
    "lead_mines_price": 2600000,
    "lead_mines_resource": {"lumber": 38000},
    "iron_mines_price": 3800000,
    "iron_mines_resource": {"lumber": 30000},
    "lumber_mills_price": 2200000,
    # Processing (Tier 2)
    "component_factories_price": 16000000,
    "component_factories_resource": {"steel": 30000, "aluminium": 30000},
    "steel_mills_price": 12000000,
    "steel_mills_resource": {"aluminium": 90000},
    "ammunition_factories_price": 10000000,
    "aluminium_refineries_price": 11000000,
    "oil_refineries_price": 9000000,
}

"""
* plus - energy or resource increase
* minus - formerly convert_minus, what resource to remove for upkeep
* money - monetary upkeep cost
* eff - effect that's added, for example pollution
*
"""
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
    # RETAIL
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
        "money": 80000,
    },
    "banks": {"plus": {"consumer_goods": 20}, "money": 220000},
    "malls": {
        "plus": {"consumer_goods": 30},
        "eff": {"pollution": 9},
        "money": 450000,
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
    "monorails": {
        "eff": {"productivity": 16},
        "effminus": {"pollution": 20},
        "money": 270000,
    },
    # MILITARY
    "army_bases": {"money": 25000},
    "harbours": {"money": 35000},
    "aerodomes": {"money": 55000},
    "admin_buildings": {"money": 90000},
    "silos": {"money": 340000},
    # INDUSTRY
    "farms": {
        "money": 3000,
        "plus": {"rations": 12},
        "eff": {"pollution": 1},
    },
    "pumpjacks": {"money": 9500, "plus": {"oil": 24}, "eff": {"pollution": 2}},
    "coal_mines": {
        "money": 4200,  # Costs $10k
        "plus": {"coal": 31},
        "eff": {"pollution": 2},
    },
    "bauxite_mines": {
        "money": 8000,  # Costs $8k
        "plus": {"bauxite": 20},
        "eff": {"pollution": 2},
    },
    "copper_mines": {
        "money": 5000,
        "plus": {"copper": 25},
        "eff": {"pollution": 2},
    },
    "uranium_mines": {
        "money": 45000,  # Costs $18k
        "plus": {"uranium": 12},
        "eff": {"pollution": 1},
    },
    "lead_mines": {
        "money": 7200,
        "plus": {"lead": 19},
        "eff": {"pollution": 2},
    },
    "iron_mines": {
        "money": 11000,
        "plus": {"iron": 23},
        "eff": {"pollution": 2},
    },
    "lumber_mills": {
        "money": 7500,
        "plus": {"lumber": 35},
        "eff": {"pollution": 1},
    },
    # PROCESSING
    "component_factories": {
        "money": 50000,  # Costs $220k
        "minus": {"copper": 20, "steel": 10, "aluminium": 15},
        "plus": {"components": 5},
        "eff": {"pollution": 5},
    },
    "steel_mills": {
        "money": 60000,
        "minus": {"coal": 35, "iron": 35},
        "plus": {"steel": 12},
        "eff": {"pollution": 4},
    },
    "ammunition_factories": {
        "money": 15000,
        "minus": {"copper": 10, "lead": 20},
        "plus": {"ammunition": 12},
        "eff": {"pollution": 3},
    },
    "aluminium_refineries": {
        "money": 42000,
        "minus": {"bauxite": 15},
        "plus": {"aluminium": 16},
        "eff": {"pollution": 3},
    },
    "oil_refineries": {
        "money": 35000,
        "minus": {"oil": 20},
        "plus": {"gasoline": 11},
        "eff": {"pollution": 6},
    },
}
