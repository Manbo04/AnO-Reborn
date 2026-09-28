"""Single source of truth for the "influence" score formula.

Influence used to be copy-pasted across helpers.py,
repositories/country_repository.py, statistics.py, app_core/coalitions and
wars/routes.py (find_targets). Every one of those now reads the score from
``influence_subquery_sql()``, which is generated from the weights below, and
``compute_influence()`` is the pure-Python mirror of the same formula (used
by tests and by the nuclear-strike preview).

The blend (rebalanced 2026-09-27, players' request):

* **Population and military are the main drivers.** Population counts per
  citizen; each unit type has its own weight, ordered carriers > cruisers >
  destroyers > submarines > bombers > fighters > helicopters > tanks >
  artillery > troops.
* **Owning missiles subtracts** a modest amount (nukes > ballistic ICBMs >
  kamikaze drones > cruise missiles): a stockpile of WMDs makes the rest of
  the world trust you less.
* **Resources are a minor share**, valued per kg (RESOURCE_VALUE_PER_KG) as
  60% hourly production + 40% stockpile. Hourly production is the nominal
  per-building output from variables.NEW_INFRA -- the same table the hourly
  revenue tick produces from -- so there is no second copy of it here.
* **Territory and buildings** (production capacity) count some.
* **Nuclear-strike penalty**: every nuke you launch stores an influence
  penalty in ``nuclear_strikes`` that decays linearly to zero over
  NUCLEAR_PENALTY_DECAY_DAYS (the struck province's recovery timer). The live
  remainder is subtracted here.

Gold no longer counts: it used to be 1 point per $100k and swamped every
other term (it was >90% of most nations' score).
"""

from __future__ import annotations

import variables

# --- Population ------------------------------------------------------------
POPULATION_WEIGHT = 0.005  # per citizen (1 point per 200 people)

# --- Military (points per unit) --------------------------------------------
UNIT_WEIGHTS = {
    "aircraft_carriers": 8000,
    "cruisers": 3000,
    "destroyers": 2000,
    "submarines": 1500,
    "bombers": 1000,
    "fighters": 800,
    "apaches": 600,  # attack helicopters
    "tanks": 300,
    "artillery": 200,
    "soldiers": 10,
    # Support units (not in the combat ordering above, small weights)
    "sam_batteries": 250,
    "spies": 100,
    "counter_intel_agents": 50,
}

# Owning missiles SUBTRACTS influence (points per missile held).
MISSILE_PENALTIES = {
    "nukes": 25000,
    "icbms": 10000,
    "kamikaze_drones": 300,
    "cruise_missiles": 200,
}

# --- Resources (minor share) -----------------------------------------------
# Value per kg, from the rebalance spec.
RESOURCE_VALUE_PER_KG = {
    "lumber": 87,
    "bauxite": 114,
    "iron": 545,
    "coal": 367,
    "copper": 302,
    "lead": 439,
    "uranium": 3980,
    "oil": 619,
    "rations": 244,
    "steel": 9244,
    "aluminium": 3813,
    "ammunition": 5100,
    "gasoline": 5639,
    "components": 155298,
}
PRODUCTION_SHARE = 0.6  # of the resource value: hourly production
STOCKPILE_SHARE = 0.4  # of the resource value: stockpile
# Scales the raw value down so resources stay a minor share (~4% of all
# influence on the 2026-09-27 prod snapshot).
RESOURCE_SCALE = 0.0000015

# --- Territory / production capacity ---------------------------------------
PROVINCE_WEIGHT = 300
CITY_WEIGHT = 10
LAND_WEIGHT = 10
BUILDING_WEIGHT = 10  # per building of any kind

# --- Nuclear penalty -------------------------------------------------------
NUCLEAR_PENALTY_DECAY_DAYS = 7


def building_hourly_value(building: str) -> float:
    """Value (per RESOURCE_VALUE_PER_KG) of one building's hourly output."""
    plus = variables.NEW_INFRA.get(building, {}).get("plus", {}) or {}
    return float(
        sum(amount * RESOURCE_VALUE_PER_KG.get(res, 0) for res, amount in plus.items())
    )


# building name -> value of one hour of its nominal output (only producers)
BUILDING_HOURLY_VALUE = {
    name: building_hourly_value(name)
    for name in variables.NEW_INFRA
    if building_hourly_value(name) > 0
}


def stockpile_value(stockpile: dict) -> float:
    return float(
        sum((qty or 0) * RESOURCE_VALUE_PER_KG.get(res, 0) for res, qty in stockpile.items())
    )


def production_value(buildings: dict) -> float:
    return float(
        sum((qty or 0) * BUILDING_HOURLY_VALUE.get(b, 0) for b, qty in buildings.items())
    )


def compute_influence(metrics: dict) -> int:
    """Pure-Python influence. Mirrors influence_subquery_sql() exactly.

    metrics keys (all optional, missing = 0):
      population, provinces, cities, land, buildings (total count),
      units: {unit_name: qty}, stockpile: {resource: kg},
      building_counts: {building_name: qty}, nuclear_penalty.
    """
    units = metrics.get("units") or {}
    score = POPULATION_WEIGHT * float(metrics.get("population") or 0)
    for name, qty in units.items():
        score += UNIT_WEIGHTS.get(name, 0) * float(qty or 0)
        score -= MISSILE_PENALTIES.get(name, 0) * float(qty or 0)
    score += RESOURCE_SCALE * (
        STOCKPILE_SHARE * stockpile_value(metrics.get("stockpile") or {})
        + PRODUCTION_SHARE * production_value(metrics.get("building_counts") or {})
    )
    score += PROVINCE_WEIGHT * float(metrics.get("provinces") or 0)
    score += CITY_WEIGHT * float(metrics.get("cities") or 0)
    score += LAND_WEIGHT * float(metrics.get("land") or 0)
    score += BUILDING_WEIGHT * float(metrics.get("buildings") or 0)
    score -= float(metrics.get("nuclear_penalty") or 0)
    return int(round(max(0.0, score)))


def nuclear_penalty_remaining(cost: float, age_seconds: float) -> float:
    """Live remainder of one strike's influence penalty (linear 7-day decay)."""
    frac = 1.0 - max(0.0, age_seconds) / (NUCLEAR_PENALTY_DECAY_DAYS * 86400.0)
    return max(0.0, float(cost) * frac)


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------


def _num(weight) -> str:
    """Plain decimal literal (never Python's 1e-05 style)."""
    if isinstance(weight, float):
        return f"{weight:.10f}".rstrip("0").rstrip(".") or "0"
    return str(weight)


def _case(column: str, mapping: dict) -> str:
    whens = " ".join(
        f"WHEN '{name}' THEN {_num(value)}" for name, value in mapping.items() if value
    )
    return f"CASE {column} {whens} ELSE 0 END"


def nuclear_penalty_sql(alias: str = "ns") -> str:
    """SQL for one nuclear_strikes row's live penalty (matches Python)."""
    return (
        f"{alias}.influence_cost * GREATEST(0, 1 - EXTRACT(EPOCH FROM (now() - "
        f"{alias}.launched_at)) / {NUCLEAR_PENALTY_DECAY_DAYS * 86400}.0)"
    )


def influence_subquery_sql(user_ids_sql: str) -> str:
    """A parenthesised SELECT returning ``(user_id, influence)`` rows.

    ``user_ids_sql`` is any SQL yielding one column of user ids (e.g.
    ``"SELECT id FROM users WHERE id = ANY(%s)"``, or a CTE name the caller
    already defined). It is inlined exactly once, so a caller passing a
    ``%s`` placeholder supplies exactly one parameter for it.

    Each aggregate is pre-grouped per user and filtered to the requested ids
    (no correlated subqueries, no full-table scans beyond those ids).
    """
    unit_points = {**UNIT_WEIGHTS}
    for name, penalty in MISSILE_PENALTIES.items():
        unit_points[name] = unit_points.get(name, 0) - penalty
    return f"""(
        WITH inf_ids AS ({user_ids_sql})
        SELECT
            ids.id AS user_id,
            ROUND(GREATEST(0,
                COALESCE(p.population, 0) * {_num(POPULATION_WEIGHT)}
                + COALESCE(m.points, 0)
                + {_num(RESOURCE_SCALE)} * (
                    {_num(STOCKPILE_SHARE)} * COALESCE(r.stock_value, 0)
                    + {_num(PRODUCTION_SHARE)} * COALESCE(b.production_value, 0))
                + COALESCE(p.provinces, 0) * {PROVINCE_WEIGHT}
                + COALESCE(p.cities, 0) * {CITY_WEIGHT}
                + COALESCE(p.land, 0) * {LAND_WEIGHT}
                + COALESCE(b.buildings, 0) * {BUILDING_WEIGHT}
                - COALESCE(n.penalty, 0)
            ))::bigint AS influence
        FROM (SELECT DISTINCT id FROM inf_ids AS x(id)) ids
        LEFT JOIN (
            SELECT userid AS user_id, COUNT(*) AS provinces,
                   SUM(citycount) AS cities, SUM(land) AS land,
                   SUM(population) AS population
            FROM provinces WHERE userid IN (SELECT id FROM inf_ids AS x(id))
            GROUP BY userid
        ) p ON p.user_id = ids.id
        LEFT JOIN (
            SELECT um.user_id,
                   SUM(um.quantity::numeric * ({_case('ud.name', unit_points)})) AS points
            FROM user_military um
            JOIN unit_dictionary ud ON ud.unit_id = um.unit_id
            WHERE um.user_id IN (SELECT id FROM inf_ids AS x(id))
            GROUP BY um.user_id
        ) m ON m.user_id = ids.id
        LEFT JOIN (
            SELECT ue.user_id,
                   SUM(ue.quantity::numeric * ({_case('rd.name', RESOURCE_VALUE_PER_KG)})) AS stock_value
            FROM user_economy ue
            JOIN resource_dictionary rd ON rd.resource_id = ue.resource_id
            WHERE ue.user_id IN (SELECT id FROM inf_ids AS x(id))
            GROUP BY ue.user_id
        ) r ON r.user_id = ids.id
        LEFT JOIN (
            SELECT ub.user_id, SUM(ub.quantity) AS buildings,
                   SUM(ub.quantity::numeric * ({_case('bd.name', BUILDING_HOURLY_VALUE)})) AS production_value
            FROM user_buildings ub
            JOIN building_dictionary bd ON bd.building_id = ub.building_id
            WHERE ub.user_id IN (SELECT id FROM inf_ids AS x(id))
            GROUP BY ub.user_id
        ) b ON b.user_id = ids.id
        LEFT JOIN (
            SELECT ns.attacker_id AS user_id, SUM({nuclear_penalty_sql('ns')}) AS penalty
            FROM nuclear_strikes ns
            WHERE ns.attacker_id IN (SELECT id FROM inf_ids AS x(id))
              AND ns.launched_at > now() - interval '{NUCLEAR_PENALTY_DECAY_DAYS} days'
            GROUP BY ns.attacker_id
        ) n ON n.user_id = ids.id
    )"""
