# File for variables that are repeated multiple times in other files
# (for example, the resources list)

DEFAULT_TAX_INCOME = 0.75
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

# Population rebalance (2026-10-04, agreed with The_kaiser in staff-chat).
#
# "Comfort" population is computed ONCE PER NATION from its total cities and
# land, on a saturating curve: BASE + CAP * (1 - exp(-units / SOFTNESS)).
# It used to be computed per province (each province had its own 1M base and
# its own curve), so splitting the same cities/land over 80 provinces gave
# ~24x the room -- province spam was the best way to grow. Initial slope is
# unchanged (~750k per city, ~120k per land); it flattens out around ~855M.
# Comfort is NOT a hard cap: growth slows to POP_GROWTH_DIMINISHING_FLOOR of
# normal past it, and distribution buildings lose effectiveness past it
# (see overcrowding_efficiency in population.py), which is what limits huge
# nations -- they have to keep building distribution or start starving.
NATION_COMFORT_BASE = 5_000_000
CITY_POP_CAP = 600_000_000
CITY_POP_SOFTNESS = 800
LAND_POP_CAP = 250_000_000
LAND_POP_SOFTNESS = 2083

# Hourly growth is based on the people a nation actually has (it used to be
# 0.15% of max population per hour no matter how many lived there, so killing
# people in a war didn't slow growth at all). growth/h =
#   rations_ratio^2 * diminishing * (POP_GROWTH_RATE * population
#                                    + POP_GROWTH_SEED_RATE * comfort)
# where diminishing = max(FLOOR, 1 - (population / comfort)^2). The small seed
# term lets new/empty nations get going.
POP_GROWTH_RATE = 0.004
POP_GROWTH_SEED_RATE = 0.00005
POP_GROWTH_DIMINISHING_FLOOR = 0.05

# Fix for distribution buildings never limiting anything: the tick compared
# "people the buildings can serve" with "rations in stock" (different units),
# so e.g. 1 food bank (250k people) "fed" a 191M nation. From this moment on
# only covered people count as fed, and past comfort every distribution
# building serves sqrt(comfort / population) of its normal amount.
# ON HOLD (2026-10-05): was set for 2026-10-06 16:00 UTC, but it changes the
# game for ~45 nations, so it goes to the weekly community vote first. If it
# passes, set a real date here (with at least 48h notice).
import datetime as _dt_rebalance

DISTRIBUTION_FIX_START = _dt_rebalance.datetime(
    2099, 1, 1, 0, 0, 0, tzinfo=_dt_rebalance.timezone.utc
)

DEFAULT_PRODUCTIVITY_PRODUCTION_MULTIPLIER = 0.009  # 9%

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

# TEMP: 48h grace period after this mechanic's 2026-08-26 rollout, so accounts
# that had already banked a surplus under the old (no-spoilage) rules get a
# window to see the announcement / adjust before spoilage actually applies.
# Safe to delete this constant and its check in population.py after this date.
import datetime as _datetime

RATIONS_SPOILAGE_GRACE_PERIOD_END = _datetime.datetime(
    2026, 8, 28, 20, 0, 0, tzinfo=_datetime.timezone.utc
)

# DEMOGRAPHIC-BASED CONSUMPTION (Phase 2)
# Rates are per-capita per tick, scaled to match building production units.
# Buildings produce single-digit resources per hour (e.g. farm → 12 rations).
# Population consumes at ~1 unit per RATIONS_PER (50k) or CONSUMER_GOODS_PER
# (80k) people, keeping demographic brackets proportional.
DEMO_RATIONS_CONSUMPTION = {
    "pop_working": 1.0 / 50000,  # ~0.00002 rations per working person per tick
    "pop_children": 1.3 / 50000,  # 30% higher for children
    "pop_elderly": 0.8 / 50000,  # slightly lower for elderly
}
DEMO_CONSUMER_GOODS_CONSUMPTION = {
    "pop_working": 1.0 / 80000,  # ~0.0000125 CG per working person per tick
    "pop_children": 1.2 / 80000,  # higher for children
    "pop_elderly": 2.0 / 80000,  # 2x for elderly (healthcare, comfort)
}

# Tax contribution by age bracket. Children are dependents (no income tax);
# elderly pay a reduced rate; working-age pays full rate.
DEMO_TAX_MULTIPLIER = {
    "pop_working": 1.0,
    "pop_children": 0.0,
    "pop_elderly": 0.45,
}

# Distribution capacity for different building types
# These cap how much rations/CG can actually be consumed even if available
CONSUMER_GOODS_DISTRIBUTION_BUILDINGS = [
    "food_banks",
    "distribution_centers",
    "malls",
    "general_stores",
    "gas_stations",
]
# Tiered capacity: mirrors rations distribution tiers
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
# Grace period (player request, .ieb 2026-09-26): until this UTC date/time,
# shipped goods still count in full so players have time to build retail in
# every province. ISO-8601; empty string disables the grace period.
PER_PROVINCE_CG_GRACE_UNTIL = "2026-10-04T12:00:00+00:00"

# Feature flag for demographic-based consumption system
FEATURE_DEMOGRAPHIC_CONSUMPTION = True  # toggle the new mechanic on/off

# Feature flag for age-weighted tax income (children/elderly pay less)
FEATURE_DEMOGRAPHIC_TAX = True  # toggle age-weighted tax rates on/off

# PHASE 3: AGING, EDUCATION & WORKFORCE (Phase 3)
# Grace period for education chain requirements: until this UTC date/time,
# if a province lacks primary schools but has higher education, its primary
# capacity is treated as max(primary, hs+uni) so players have time to build.
EDUCATION_CHAIN_GRACE_UNTIL = "2026-10-05T00:00:00+00:00"

# Daily population aging rates (per tick, as fraction)
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

# Education distribution (when children graduate)
# Determined by available school/university capacity in province
EDUCATION_GRADUATION_PRIORITY = [
    "universities",  # If capacity available -> edu_college
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

# Feature flag for Phase 3 (workforce/employment system)
FEATURE_PHASE3_WORKFORCE = True

# Game visuals (hybrid UI) — defaults on; override via env FEATURE_GAME_SHELL=false etc.
# See game_ui.py for env parsing and layout helpers.

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
# Per templates/mechanics.html, this policy is documented to affect
# "Industrial Districts, Factories, Steel Mills, Power Plants" -- i.e. every
# building in the "electricity" category (INFRA_TYPE_BUILDINGS["electricity"])
# and both *_factories buildings, not just coal/oil burners and
# component_factories. Previously only 2 of the 7 power plant types (and 1 of
# the 2 factory types) were listed, so nations running on hydro/nuclear/solar/
# wind/geothermal power (a very common late-game choice, since those are the
# only power plants with zero pollution to begin with) saw no upkeep discount
# at all from this policy -- matching the player report that expenses never
# actually went down.
POLICY_SUBSIDIES_AFFECTED_BUILDINGS = [
    "industrial_district",
    "component_factories",
    "ammunition_factories",
    "steel_mills",
    "coal_burners",
    "oil_burners",
    "hydro_dams",
    "nuclear_reactors",
    "solar_fields",
    "wind_farms",
    "geothermal_plants",
]

POLICY_RATIONING_CONSUMPTION_REDUCTION = 0.85  # -15% rations consumption
POLICY_RATIONING_HAPPINESS_PENALTY = 10  # -10 happiness per province

UNITS = [
    "soldiers",
    "tanks",
    "artillery",
    "sam_batteries",
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

ENERGY_UNITS = [
    "coal_burners",
    "oil_burners",
    "hydro_dams",
    "nuclear_reactors",
    "solar_fields",
    "wind_farms",
    "geothermal_plants",
]

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

UPGRADES = {"oil_burners"}

# Dictionary for which units give what resources, etc ()
INFRA = {  # Display values — synced to NEW_INFRA engine values (units/hr per building)
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
    "solar_fields_money": 13000,
    "wind_farms_plus": {"energy": 2},
    "wind_farms_money": 8000,
    "geothermal_plants_plus": {"energy": 5},
    "geothermal_plants_money": 20000,
    ####################
    # Retail — synced to NEW_INFRA engine values
    "food_banks_plus": {"consumer_goods": 2},
    "food_banks_money": 2500,
    "distribution_centers_plus": {"consumer_goods": 8},
    "distribution_centers_money": 15000,
    "gas_stations_plus": {"consumer_goods": 12},
    "gas_stations_effect": [{"pollution": 4}],
    "gas_stations_money": 20000,
    "general_stores_plus": {"consumer_goods": 10},
    "general_stores_effect": [{"pollution": 2}],
    "general_stores_money": 37500,
    "farmers_markets_plus": {"consumer_goods": 16},
    "farmers_markets_effect": [{"pollution": 5}],
    "farmers_markets_money": 48000,
    "banks_plus": {"consumer_goods": 20},
    "banks_money": 100000,
    "malls_plus": {"consumer_goods": 30},
    "malls_effect": [{"pollution": 9}],
    "malls_money": 150000,
    "industrial_district_plus": {"consumer_goods": 50},
    "industrial_district_effect": [{"pollution": 15}],
    "industrial_district_money": 85000,
    "workshops_plus": {"consumer_goods": 4},
    "workshops_convert_minus": [{"steel": 2}],
    "workshops_effect": [{"pollution": 1}],
    "workshops_money": 12000,
    "jewelry_stores_plus": {"consumer_goods": 36},
    "jewelry_stores_convert_minus": [
        {"silver": 12},
        {"diamonds": 6},
        {"bullion": 8},
    ],
    "jewelry_stores_effect": [{"pollution": 2}],
    "jewelry_stores_money": 60000,
    "automotive_plants_plus": {"consumer_goods": 160},
    "automotive_plants_convert_minus": [
        {"steel": 40},
        {"aluminium": 30},
        {"components": 15},
    ],
    "automotive_plants_effect": [{"pollution": 12}],
    "automotive_plants_money": 180000,
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
    "primary_school_effect": [{"productivity": 2}, {"happiness": 2}],
    "primary_school_money": 30000,
    "high_school_effect": [{"productivity": 5}, {"happiness": 3}],
    "high_school_money": 75000,
    "monorails_effect": [{"productivity": 16}],
    "monorails_effect_minus": {"pollution": 20},
    "monorails_money": 270000,
    "railways_effect": [{"productivity": 8, "pollution": 2}],
    "railways_money": 67500,
    "metros_effect": [{"productivity": 12}],
    "metros_effect_minus": {"pollution": 10},
    "metros_money": 150000,
    "firewatch_towers_money": 1000,
    "levees_money": 3000,
    "seismic_reinforcements_money": 5000,
    ###################
    # Military (Done)
    "army_bases_money": 25000,  # Costs $25k
    "harbours_money": 35000,
    "aerodomes_money": 55000,
    "admin_buildings_money": 90000,
    "silos_money": 340000,
    "drone_sites_money": 5000,
    "missile_batteries_money": 40000,
    ################
    # Industry — synced to NEW_INFRA engine values
    "farms_money": 3000,
    "farms_plus": {"rations": 100},
    "farms_effect": [{"pollution": 1}],
    "fisheries_money": 1800,
    "fisheries_plus": {"rations": 160},
    "fisheries_effect": [{"pollution": 1}],
    "pumpjacks_money": 9500,
    "pumpjacks_plus": {"oil": 100},
    "pumpjacks_effect": [{"pollution": 2}],
    "coal_mines_money": 4200,
    "coal_mines_plus": {"coal": 120},
    "coal_mines_effect": [{"pollution": 2}],
    "bauxite_mines_money": 8000,
    "bauxite_mines_plus": {"bauxite": 260},
    "bauxite_mines_effect": [{"pollution": 2}],
    "copper_mines_money": 5000,
    "copper_mines_plus": {"copper": 120},
    "copper_mines_effect": [{"pollution": 2}],
    "uranium_mines_money": 45000,
    "uranium_mines_plus": {"uranium": 40},
    "uranium_mines_effect": [{"pollution": 1}],
    "lead_mines_money": 7200,
    "lead_mines_plus": {"lead": 80},
    "lead_mines_effect": [{"pollution": 2}],
    "iron_mines_money": 11000,
    "iron_mines_plus": {"iron": 70},
    "iron_mines_effect": [{"pollution": 2}],
    "lumber_mills_money": 7500,
    "lumber_mills_plus": {"lumber": 150},
    "lumber_mills_effect": [{"pollution": 1}],
    "silver_mines_money": 12000,
    "silver_mines_plus": {"silver": 60},
    "silver_mines_effect": [{"pollution": 2}],
    "diamond_mines_money": 25000,
    "diamond_mines_plus": {"diamonds": 30},
    "diamond_mines_effect": [{"pollution": 2}],
    "bullion_mines_money": 18000,
    "bullion_mines_plus": {"bullion": 40},
    "bullion_mines_effect": [{"pollution": 2}],
    ################
    # Processing — synced to NEW_INFRA engine values
    "component_factories_money": 50000,
    "component_factories_convert_minus": [
        {"copper": 80},
        {"steel": 40},
        {"aluminium": 60},
    ],
    "component_factories_plus": {"components": 20},
    "component_factories_effect": [{"pollution": 5}],
    "steel_mills_money": 60000,
    "steel_mills_convert_minus": [{"coal": 38}, {"iron": 67}],
    "steel_mills_plus": {"steel": 48},
    "steel_mills_effect": [{"pollution": 4}],
    "ammunition_factories_money": 15000,
    "ammunition_factories_convert_minus": [{"copper": 40}, {"lead": 80}],
    "ammunition_factories_plus": {"ammunition": 48},
    "ammunition_factories_effect": [{"pollution": 3}],
    "aluminium_refineries_money": 42000,
    "aluminium_refineries_convert_minus": [{"bauxite": 256}],
    "aluminium_refineries_plus": {"aluminium": 64},
    "aluminium_refineries_effect": [{"pollution": 3}],
    "oil_refineries_money": 35000,
    "oil_refineries_convert_minus": [{"oil": 88}],
    "oil_refineries_plus": {"gasoline": 44},
    "oil_refineries_effect": [{"pollution": 6}],
}

MILDICT = {
    # LAND
    # Resource costs synced with unit_dictionary (production_cost_* columns)
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
}

# Per-unit resources consumed when a drone_site/missile_battery manufactures
# one unit into the stockpile (hourly tick), and the gasoline burned per
# launch. Kept in one place since both numbers are cross-referenced by
# migrations/0066_drone_missile_carrier_units.sql -- if either changes here,
# update that migration's unit_dictionary seed to match.
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
    "primary_school_price": 4000000,
    "primary_school_resource": {"steel": 25000, "aluminium": 15000, "lumber": 40000},
    "high_school_price": 12000000,
    "high_school_resource": {"steel": 60000, "aluminium": 40000, "lumber": 80000},
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

# National loans (borrowing against the nation's own population-scaled
# capacity). One active loan per nation at a time -- see app_core/loans/.
# Redesigned 2026-09-07 (Discord #suggestions "Kurai suggestions") from
# hourly-compounding interest to a one-time origination fee, to avoid the
# "build cities, borrow against growth, repeat" glitch Kurai flagged while
# still being friendlier to new players than an ongoing hourly drain.
LOAN_CAP_PER_POPULATION = 40  # $ of borrowing capacity per population point
LOAN_MIN_AMOUNT = 100_000
LOAN_ORIGINATION_FEE = 0.10  # one-time fee added to principal at issuance
LOAN_HIGH_UTILIZATION_THRESHOLD = 0.70  # fraction of borrowing cap
LOAN_HIGH_UTILIZATION_FEE = 0.15  # fee charged instead of LOAN_ORIGINATION_FEE above the threshold
LOAN_COOLDOWN_HOURS = 24  # can't take a new loan until this long after fully repaying the last one

# Loan credit score (Kurai, #suggestions 2026-09-07): repaying on time raises
# the borrowing cap a little, paying late / sitting in default lowers it.
# Scored over the nation's last LOAN_CREDIT_WINDOW loans, see
# app_core/loans/services.py::score_loan_history. Points are percent of cap.
LOAN_TERM_DAYS = 7  # a loan repaid within this many days counts as "on time"
LOAN_DEFAULT_DAYS = 21  # outstanding longer than this = in default
LOAN_CREDIT_WINDOW = 10  # only the most recent N loans count
LOAN_CREDIT_ON_TIME_POINTS = 5  # per full-size on-time loan
LOAN_CREDIT_FULL_SIZE_SHARE = 0.25  # loan must be >= 25% of cap to earn full on-time points
LOAN_CREDIT_LATE_POINTS = -5  # repaid after LOAN_TERM_DAYS, or currently overdue
LOAN_CREDIT_DEFAULT_REPAID_POINTS = -10  # repaid only after LOAN_DEFAULT_DAYS
LOAN_CREDIT_IN_DEFAULT_POINTS = -15  # still outstanding past LOAN_DEFAULT_DAYS
LOAN_CREDIT_MAX_POINTS = 25  # cap multiplier bounded to [0.75, 1.25]

# Player-to-player Bonds market (Discord #suggestions "Bonds market" from
# Kurai, 2026-09-16) -- deliberately separate from the national-loan system
# above: here one player funds another player's bond directly. The issuer
# sets rate+term before it sells; once funded it can't be cashed out early;
# daily interest is auto-deducted to the lender by
# app_core/game_ticks/bond_tick.py; an issuer may opt into auto-escrow to
# amortize principal daily instead of owing it as a lump sum at maturity.
# See app_core/bonds/ and migration 0079_add_bonds_market.sql.
BOND_CAP_PER_POPULATION = 30  # $ of total outstanding (listed+active) bond principal per population point

# Market / trade fees (app_core/market/fees.py). Charged to whoever completes
# a money trade (buying from a sell offer, filling a buy offer, accepting a
# direct trade) on top of / out of the traded amount, and removed from the
# economy -- simulates transport costs.
TRADE_FEE_PERCENT = 5
# Reduced fee between two members of the same currency union.
UNION_TRADE_FEE_PERCENT = 2

# Currency unions (app_core/currency_unions). Benefits only apply while the
# union has at least CURRENCY_UNION_MIN_MEMBERS members.
CURRENCY_UNION_MIN_MEMBERS = 2
CURRENCY_UNION_BOND_CAP_MULTIPLIER = 1.25  # +25% bond issuance cap
CURRENCY_UNION_NAME_MAX = 60
CURRENCY_UNION_CURRENCY_MAX = 40
BOND_MIN_PRINCIPAL = 50_000
BOND_MIN_INTEREST_RATE = 0.001  # 0.1%/day
BOND_MAX_INTEREST_RATE = 0.02   # 2%/day
BOND_MIN_TERM_DAYS = 3
BOND_MAX_TERM_DAYS = 30
BOND_MAX_DEFAULT_STRIKES = 3    # missed daily interest payments before a bond is force-defaulted early instead of waiting for maturity
BOND_DEFAULT_COOLDOWN_DAYS = 14  # can't issue a new bond this long after defaulting on one

# National currency (central bank) -- see app_core/currency/. Discord
# #suggestions ("national currency", Kurai, 2026-09-16): each nation can
# convert its own gold into its own currency (display name is the existing
# cosmetic users.currency_name field) and back, at this single fixed global
# rate. The rate is intentionally NOT player-adjustable: because it never
# changes, minting and redeeming are exactly value-neutral round-trip
# (5 gold -> 1 currency -> 5 gold), so there's no window where changing a
# rate between two conversions could mint gold from nothing.
CURRENCY_GOLD_PER_UNIT = 5  # gold cost to mint 1 unit of national currency; same rate redeems it back
