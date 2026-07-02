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
        "city_parks",
        "hospitals",
        "libraries",
        "universities",
        "monorails",
        "primary_school",
        "high_school",
        "industrial_district",
    }
)

LAND_UNITS = frozenset(
    {
        "army_bases",
        "harbours",
        "aerodomes",
        "admin_buildings",
        "silos",
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
        return "{:,.1f}".format(num)
    if num < 1000000:
        k = num / 1000
        if k == int(k):
            return "{:,}K".format(int(k))
        return "{:,.1f}".format(k).rstrip("0").rstrip(".") + "K"
    if num < 1000000000:
        m = num / 1000000
        if m == int(m):
            return "{}M".format(int(m))
        return "{:.1f}M".format(m).rstrip("0").rstrip(".")
    b = num / 1000000000
    if b == int(b):
        return "{}B".format(int(b))
    return "{:.1f}B".format(b).rstrip("0").rstrip(".")


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
        return "{:,.1f} kg".format(num)
    if num < 1000000:
        t = num / 1000
        if t == int(t):
            return "{:,} t".format(int(t))
        return "{:,.1f} t".format(t)
    if num < 1000000000:
        kt = num / 1000000
        if kt == int(kt):
            return "{:,} kt".format(int(kt))
        return "{:,.1f} kt".format(kt)
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
