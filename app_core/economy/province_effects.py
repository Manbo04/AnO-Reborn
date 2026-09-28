"""Per-building province stat effects (happiness, pollution, productivity).

Shared by the hourly revenue tick (app_core/game_ticks/revenue.py) and the
province page's "what makes up this number" breakdown, so the two can't
drift apart.

Pollution clamp order (Kurai/ieb report, 2026-09-20): the tick used to clamp
pollution to 0..100 after EVERY building type. With 200 polluting mines the
running value hit 100, the overflow was thrown away, and a single park then
knocked it down to 94 -- as if the mines' extra pollution never existed.
Pollution now accumulates uncapped through the whole building pass (additions
and reductions alike) and is clamped once, at the end, when the province row
is written.
"""

import variables

# Stats whose 0..100 clamp is deferred until the end of the tick's building
# pass instead of being applied after every building type.
DEFERRED_CLAMP_STATS = frozenset({"pollution"})

EFFECT_STATS = ("happiness", "pollution", "productivity")


def unit_category(unit):
    for name, members in variables.INFRA_TYPE_BUILDINGS.items():
        if unit in members:
            return name
    return False


def clamp_percentage(value):
    return min(100, max(0, value))


def building_effects_per_unit(unit, upgrades, policies):
    """Return (eff, effminus) for ONE unit of `unit`, with every upgrade and
    policy modifier the tick applies. Values may be fractional; callers
    multiply by the unit count and then round with effect_total()."""
    infra = variables.NEW_INFRA.get(unit, {})
    eff = dict(infra.get("eff", {}) or {})
    effminus = dict(infra.get("effminus", {}) or {})
    upgrades = upgrades or {}
    policies = policies or []

    if unit == "universities" and 3 in policies:
        eff["productivity"] *= 1.10
        eff["happiness"] *= 1.10

    if unit == "hospitals" and upgrades.get("nationalhealthinstitution"):
        eff["happiness"] = int(eff["happiness"] * 1.3)

    if unit == "monorails" and upgrades.get("highspeedrail"):
        eff["productivity"] = int(eff["productivity"] * 1.2)

    if "pollution" in eff:
        # GOVERNMENT REGULATION: retail pollutes 25% less.
        if unit_category(unit) == "retail" and upgrades.get("governmentregulation"):
            eff["pollution"] *= 0.75
        # INDUSTRIAL SUBSIDIES policy: affected buildings pollute more.
        if (
            variables.POLICY_INDUSTRIAL_SUBSIDIES in policies
            and unit in variables.POLICY_SUBSIDIES_AFFECTED_BUILDINGS
        ):
            eff["pollution"] *= variables.POLICY_SUBSIDIES_POLLUTION_MULTIPLIER

    return eff, effminus


def effect_total(per_unit, count):
    """Total effect of `count` running units, rounded the way the tick does."""
    return int(round(per_unit * count))


def apply_effect(current, eff_name, amount, sign, percentage_based):
    """Apply one building type's effect to a province stat.

    Pollution (DEFERRED_CLAMP_STATS) is left unclamped here so reductions
    act on the real, uncapped total; the caller clamps it once at the end
    with clamp_percentage(). Other percentage stats keep their existing
    per-step clamp."""
    new_value = current + amount if sign == "+" else current - amount
    if eff_name in DEFERRED_CLAMP_STATS:
        return new_value
    if eff_name in percentage_based:
        return clamp_percentage(new_value)
    return max(0, new_value)


def province_stat_breakdown(
    current,
    units,
    upgrades,
    policies,
    unemployment_penalty=0,
):
    """Explain a province's happiness/pollution/productivity for display.

    `current` is {stat: stored value}. Returns {stat: {"current", "sources",
    "net", "projected"}}, where sources are {"name", "count", "per_unit",
    "total"} (total is signed, per hour, assuming every built unit runs --
    buildings idled by missing money/power/inputs contribute nothing in the
    real tick). "projected" replays the tick's exact order: building types
    in variables.BUILDINGS order (additions then reductions each), then the
    unemployment penalty, then policy happiness modifiers.
    """
    policies = policies or []
    percentage_based = ("happiness", "productivity", "consumer_spending", "pollution")
    result = {
        stat: {"current": int(current.get(stat) or 0), "sources": [], "net": 0}
        for stat in EFFECT_STATS
    }
    running = {stat: current.get(stat) or 0 for stat in EFFECT_STATS}

    for unit in variables.BUILDINGS:
        count = int(units.get(unit, 0) or 0)
        if count <= 0:
            continue
        eff, effminus = building_effects_per_unit(unit, upgrades, policies)
        for stat, per_unit in eff.items():
            if stat not in result:
                continue
            total = effect_total(per_unit, count)
            running[stat] = apply_effect(running[stat], stat, total, "+", percentage_based)
            result[stat]["sources"].append(
                {"name": unit, "count": count, "per_unit": per_unit, "total": total}
            )
        for stat, per_unit in effminus.items():
            if stat not in result:
                continue
            total = effect_total(per_unit, count)
            running[stat] = apply_effect(running[stat], stat, total, "-", percentage_based)
            result[stat]["sources"].append(
                {"name": unit, "count": count, "per_unit": -per_unit, "total": -total}
            )

    happiness_extras = []
    if unemployment_penalty:
        happiness_extras.append(("High unemployment", -unemployment_penalty))
        running["happiness"] = max(0, running["happiness"] - unemployment_penalty)
    if variables.POLICY_UNIVERSAL_HEALTHCARE in policies:
        bonus = variables.POLICY_HEALTHCARE_HAPPINESS_BONUS
        happiness_extras.append(("Universal Healthcare policy", bonus))
        running["happiness"] = min(100, running["happiness"] + bonus)
    if variables.POLICY_MANDATORY_SCHOOLING in policies:
        bonus = variables.POLICY_SCHOOLING_HAPPINESS_BONUS
        happiness_extras.append(("Mandatory Schooling policy", bonus))
        running["happiness"] = min(100, running["happiness"] + bonus)
    if variables.POLICY_RATIONING_PROGRAM in policies:
        penalty = variables.POLICY_RATIONING_HAPPINESS_PENALTY
        happiness_extras.append(("Rationing Program policy", -penalty))
        running["happiness"] = max(0, running["happiness"] - penalty)
    for label, total in happiness_extras:
        result["happiness"]["sources"].append(
            {"name": None, "label": label, "count": None, "per_unit": None, "total": total}
        )

    for stat in EFFECT_STATS:
        entry = result[stat]
        entry["net"] = sum(s["total"] for s in entry["sources"])
        entry["projected"] = int(clamp_percentage(running[stat]))
    return result


def pop_cap_marginals(cities, land):
    """Max-population numbers behind the city/land tooltips.

    Cities and land raise max population on a saturating curve (see
    calc_province_population_delta): cap * (1 - exp(-n / softness)). Each
    extra city/land adds less than the one before. Returns what the NEXT
    one adds right now, the total from cities/land so far, the curve caps,
    and the "diminishing returns" thresholds: at `softness` owned you have
    ~63% of the cap, at 3x softness ~95% (after that more barely helps).
    """
    import math

    def curve(cap, softness, n):
        return cap * (1 - math.exp(-max(0, n) / softness))

    cities = int(cities or 0)
    land = int(land or 0)
    c_cap, c_soft = variables.CITY_POP_CAP, variables.CITY_POP_SOFTNESS
    l_cap, l_soft = variables.LAND_POP_CAP, variables.LAND_POP_SOFTNESS
    return {
        "city_next": int(curve(c_cap, c_soft, cities + 1) - curve(c_cap, c_soft, cities)),
        "city_total": int(curve(c_cap, c_soft, cities)),
        "city_cap": int(c_cap),
        "city_soft": int(c_soft),
        "city_95": int(round(3 * c_soft)),
        "land_next": int(curve(l_cap, l_soft, land + 1) - curve(l_cap, l_soft, land)),
        "land_total": int(curve(l_cap, l_soft, land)),
        "land_cap": int(l_cap),
        "land_soft": int(l_soft),
        "land_95": int(round(3 * l_soft)),
        # Land's tax bonus is linear and stops growing at this many land.
        "land_tax_max": int(1 + round(1 / variables.DEFAULT_LAND_TAX_MULTIPLIER)),
    }
