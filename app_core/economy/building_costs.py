"""Canonical build costs from PROVINCE_UNIT_PRICES — display + purchase."""
from __future__ import annotations

import variables

BUILDING_DISPLAY_NAMES = {
    "coal_burners": "Coal power plants",
    "oil_burners": "Oil power plants",
}

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


def format_money(value) -> str:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    if num < 0:
        return "-" + format_money(abs(num))
    if num < 10000:
        if num == int(num):
            return "{:,}".format(int(num))
        return "{:,.2f}".format(num)
    if num < 1000000:
        k = num / 1000
        if k == int(k):
            return "{:,}K".format(int(k))
        return "{:,.2f}".format(k).rstrip("0").rstrip(".") + "K"
    if num < 1000000000:
        m = num / 1000000
        if m == int(m):
            return "{}M".format(int(m))
        return "{:.2f}M".format(m).rstrip("0").rstrip(".")
    b = num / 1000000000
    if b == int(b):
        return "{}B".format(int(b))
    return "{:.2f}B".format(b).rstrip("0").rstrip(".")


def format_weight(value) -> str:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    if num < 0:
        return "-" + format_weight(abs(num))
    if num < 1000:
        if num == int(num):
            return "{:,} kg".format(int(num))
        return "{:,.2f} kg".format(num)
    if num < 1000000:
        t = num / 1000
        if t == int(t):
            return "{:,} t".format(int(t))
        return "{:,.2f} t".format(t)
    if num < 1000000000:
        kt = num / 1000000
        if kt == int(kt):
            return "{:,} kt".format(int(kt))
        return "{:,.2f} kt".format(kt)
    mt = num / 1000000000
    if mt == int(mt):
        return "{:,} Mt".format(int(mt))
    return "{:.1f} Mt".format(mt)


def _normalize_building_name(unit: str) -> str:
    raw = (unit or "").strip().lower()
    if "," in raw:
        raw = raw.split(", ")[0]
    renames = {"fulfillment centers": "malls", "bullet trains": "monorails"}
    label = raw.replace("_", " ")
    if label == "coal burners":
        return "coal_burners"
    try:
        return renames[label]
    except KeyError:
        return raw.replace(" ", "_") if " " in raw else raw


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


def get_slot_type(building_name: str) -> str | None:
    name = _normalize_building_name(building_name)
    if name in CITY_UNITS:
        return "city"
    if name in LAND_UNITS:
        return "land"
    return None


def building_info(name: str) -> dict:
    """What a building does, from the same tables the tick uses: workers it
    employs, upkeep, what it produces/consumes and side effects. Shown as the
    "i" info on building cards (weekly vote 10-09 / 10-16)."""
    import variables

    infra = variables.NEW_INFRA.get(name) or {}
    matrix = variables.BUILDING_EMPLOYMENT_MATRICES.get(name) or {}
    return {
        "employs": int(matrix.get("worker_count", 0) or 0),
        "upkeep": int(infra.get("money", 0) or 0),
        "produces": dict(infra.get("plus") or {}),
        "consumes": dict(infra.get("minus") or {}),
        "effects": dict(infra.get("eff") or {}),
    }


def building_info_text(name: str, employs_only: bool = False) -> str:
    """One-line player-facing version of building_info().

    Output/upkeep shown here are the BASE values; the classic province cards
    already print upgrade-adjusted numbers, so they use employs_only=True to
    avoid two different figures on one card."""
    info = building_info(name)

    def pretty(d, sign=""):
        return ", ".join(f"{sign}{v:,} {k.replace('_', ' ')}" for k, v in d.items())

    parts = []
    if info["employs"]:
        edu = education_requirement(name)
        parts.append(
            f"Employs {info['employs']:,} workers" + (f" ({edu})" if edu else "")
        )
    if employs_only:
        return " · ".join(parts)
    if info["upkeep"]:
        parts.append(f"base upkeep ${info['upkeep']:,}/h")
    if info["produces"]:
        parts.append("base output " + pretty(info["produces"]))
    if info["consumes"]:
        parts.append("uses " + pretty(info["consumes"]))
    if info["effects"]:
        parts.append("effects: " + pretty(info["effects"], "+"))
    return " · ".join(parts)


EDUCATION_LABELS = {
    "edu_none": "No schooling",
    "edu_highschool": "High school",
    "edu_college": "College",
}

_PERCENT_STATS = ("happiness", "productivity", "consumer_spending", "pollution")


def education_requirement(name: str) -> str:
    """Worker education the building hires, from the same employment matrix
    the workforce tick uses (e.g. "No schooling", "80% High school, 20% College")."""
    import variables

    edu = (variables.BUILDING_EMPLOYMENT_MATRICES.get(name) or {}).get("education") or {}
    shares = [(k, v) for k, v in edu.items() if v]
    if len(shares) == 1:
        return EDUCATION_LABELS.get(shares[0][0], shares[0][0])
    return ", ".join(
        f"{round(v * 100):g}% {EDUCATION_LABELS.get(k, k)}" for k, v in shares
    )


def _distribution_capacity(name: str) -> dict:
    import variables

    out = {}
    rations = getattr(variables, "RATIONS_DISTRIBUTION_PER_BUILDING", {}) or {}
    goods = getattr(variables, "CONSUMER_GOODS_DISTRIBUTION_PER_BUILDING", {}) or {}
    if name in rations:
        out["rations"] = int(rations[name])
    if name in goods:
        out["consumer goods"] = int(goods[name])
    return out


def building_description(
    name: str, upgrades: dict | None = None, policies: list | None = None
) -> str:
    """Single player-facing description of a building, generated from the
    tables the tick uses (NEW_INFRA, the employment matrix, build prices,
    province_effects). Replaces the hand-written per-building sentences that
    mixed build cost, base upkeep and upgrade-adjusted numbers under one word
    "cost" (Discord "I Am Confusion", Andy). Every figure is labelled; where an
    upgrade changes it, both the base and the adjusted figure are shown."""
    import variables
    from app_core.economy.project_bonuses import PROJECT_OUTPUT_BONUSES
    from app_core.economy.province_effects import building_effects_per_unit

    name = _normalize_building_name(name)
    infra = variables.NEW_INFRA.get(name)
    if not infra:
        return ""
    upgrades = upgrades or {}

    def res_text(d, sign=""):
        out = []
        for k, v in d.items():
            label = k.replace("_", " ")
            amount = format_weight(v) if k in variables.RESOURCES else f"{v:,}"
            out.append(f"{sign}{amount} {label}")
        return ", ".join(out)

    parts = []
    try:
        cost = get_build_cost(name, policies)
        build = f"${format_money(cost['gold'])}"
        if cost["resources"]:
            build += " + " + res_text(cost["resources"])
        parts.append(f"Build cost {build}")
    except KeyError:
        pass

    upkeep = int(infra.get("money", 0) or 0)
    if upkeep:
        text = f"Upkeep ${upkeep:,}/h"
        category = next(
            (c for c, names in variables.INFRA_TYPE_BUILDINGS.items() if name in names),
            None,
        )
        if category == "industry" and upgrades.get("cheapermaterials"):
            text += f" (${int(upkeep * 0.8):,}/h with Cheaper Materials)"
        elif name == "malls" and upgrades.get("onlineshopping"):
            text += f" (${int(upkeep * 0.7):,}/h with Online Shopping)"
        parts.append(text)

    matrix = variables.BUILDING_EMPLOYMENT_MATRICES.get(name) or {}
    if matrix.get("worker_count"):
        edu = education_requirement(name)
        parts.append(
            f"Employs {int(matrix['worker_count']):,} workers"
            + (f" ({edu})" if edu else "")
        )

    plus = dict(infra.get("plus") or {})
    if plus:
        text = "Base output " + res_text(plus) + "/h"
        if name == "farms":
            text += (
                f" + {format_weight(variables.LAND_FARM_PRODUCTION_ADDITION)}"
                " per acre of land"
            )
        bonus = PROJECT_OUTPUT_BONUSES.get(name)
        if bonus and upgrades.get(bonus[0]):
            text += f" (+{round(bonus[1] * 100):g}% from your national project)"
        parts.append(text)

    # Input multipliers the tick applies (revenue.py "Per-unit resource cost").
    input_mult = 1.0
    if name == "component_factories" and upgrades.get("automationintegration"):
        input_mult *= 0.75
    if name == "steel_mills":
        if upgrades.get("largerforges"):
            input_mult *= 0.7
        if upgrades.get("integratedsteelmaking"):
            input_mult *= 1.36
        if upgrades.get("electricarcfurnace"):
            input_mult *= 0.5
    minus = {k: round(v * input_mult) for k, v in (infra.get("minus") or {}).items()}
    if minus:
        parts.append("Uses " + res_text(minus) + "/h")
    if name == "steel_mills" and upgrades.get("electricarcfurnace"):
        energy = 2
    else:
        energy = 1 if name in variables.ENERGY_CONSUMERS else 0
    if energy:
        parts.append(f"Uses {energy} electricity/h")
    capacity = _distribution_capacity(name)
    if capacity:
        parts.append(
            "Distribution capacity "
            + ", ".join(f"{v:,} {k}" for k, v in capacity.items())
        )

    eff, effminus = building_effects_per_unit(name, upgrades, policies or [])
    effects = []
    for k, v in eff.items():
        effects.append(f"+{v:g}{'%' if k in _PERCENT_STATS else ''} {k.replace('_', ' ')}")
    for k, v in effminus.items():
        effects.append(f"-{v:g}{'%' if k in _PERCENT_STATS else ''} {k.replace('_', ' ')}")
    if effects:
        parts.append("Effects: " + ", ".join(effects))
    return " · ".join(parts)


def enrich_building_row(row: dict, policies: list | None = None) -> dict:
    """Attach canonical cost fields to a building_dictionary row."""
    name = row.get("name") or ""
    try:
        cost = get_build_cost(name, policies)
    except KeyError:
        cost = {
            "gold": 0,
            "resources": {},
            "cost_display": row.get("display_name") or name,
        }
    out = dict(row)
    out["gold_cost"] = cost["gold"]
    out["resource_cost"] = cost["resources"]
    out["cost_display"] = cost["cost_display"]
    out["info"] = building_info_text(name)
    return out


# Land / city expansion pricing. Each extra city or land costs a bit more
# than the last (linear), up to a price ceiling after CAP_THRESHOLD owned.
LAND_CITY_PRICING = {
    # unit: (base_price, increment_per_owned, cap_threshold)
    "cityCount": (750000, 50000, 200),
    "land": (520000, 25000, 100),
}


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
