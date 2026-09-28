"""Canonical build costs from PROVINCE_UNIT_PRICES — display + purchase."""
from __future__ import annotations

import variables

BUILDING_DISPLAY_NAMES = {
    "coal_burners": "Coal power plants",
    "oil_burners": "Oil power plants",
    "malls": "Fulfillment centers",
    "monorails": "Bullet trains",
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
    unit: str, current_owned: int, num_purchased: int, policies: list | None = None
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
    return int(apply_policy_gold_discount(unit, raw, policies))
