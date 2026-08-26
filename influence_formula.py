"""Single source of truth for the "influence" score formula.

Influence used to be copy-pasted (with matching but independently editable
coefficients) across helpers.py, repositories/country_repository.py, and
app_core/coalitions/routes.py. This module centralizes the coefficients so a
balance change only has to happen in one place.
"""

INFLUENCE_WEIGHTS = {
    "provinces": 300,
    "soldiers": 0.02,
    "artillery": 1.6,
    "tanks": 0.8,
    "fighters": 3.5,
    "bombers": 2.5,
    "apaches": 3.2,
    "submarines": 4.5,
    "destroyers": 3,
    "cruisers": 5.5,
    "icbms": 250,
    "nukes": 500,
    "spies": 25,
    "cities": 10,
    "land": 10,
    "resources": 0.001,
    "gold": 0.00001,
}

# Column references shared by the SQL call sites that join provinces (p),
# military (m), resources (r), and stats (s) with those exact aliases.
STANDARD_INFLUENCE_ALIASES = {
    "provinces": "p.provinces_count",
    "soldiers": "m.soldiers",
    "artillery": "m.artillery",
    "tanks": "m.tanks",
    "fighters": "m.fighters",
    "bombers": "m.bombers",
    "apaches": "m.apaches",
    "submarines": "m.submarines",
    "destroyers": "m.destroyers",
    "cruisers": "m.cruisers",
    "icbms": "m.icbms",
    "nukes": "m.nukes",
    "spies": "m.spies",
    "cities": "p.city_count",
    "land": "p.total_land",
    "resources": "r.total_resources",
    "gold": "s.gold",
}


def _format_weight(weight) -> str:
    """Render a weight as a plain decimal literal (never Python's 1e-05 style)."""
    if isinstance(weight, float):
        return f"{weight:.10f}".rstrip("0").rstrip(".")
    return str(weight)


def compute_influence(metrics: dict) -> int:
    """Compute the influence score from a dict of raw metric values.

    `metrics` keys should match INFLUENCE_WEIGHTS; missing keys count as 0.
    """
    return round(
        sum(metrics.get(key, 0) * weight for key, weight in INFLUENCE_WEIGHTS.items())
    )


def influence_sql_expr(aliases: dict) -> str:
    """Build a `ROUND(...)::bigint` SQL expression for the influence formula.

    `aliases` must map every INFLUENCE_WEIGHTS key to a SQL column reference
    (e.g. "m.soldiers"). Raises KeyError if a key is missing, so a query
    fails loudly at query-build time instead of silently under-scoring.
    """
    terms = [
        f"COALESCE({aliases[key]}, 0) * {_format_weight(weight)}"
        for key, weight in INFLUENCE_WEIGHTS.items()
    ]
    return "ROUND(\n    " + "\n    + ".join(terms) + "\n)::bigint"
