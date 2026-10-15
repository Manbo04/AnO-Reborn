"""War range by strength logic and database helpers.

Replaces the old province-count war range with a strength range:
You can only declare war on nations whose strength is between
75% and 133% of your population-based strength.

War-range strength = population / 1000. Standing units affect combat, not eligibility.
"""
from __future__ import annotations

WAR_RANGE_LOW = 0.75
WAR_RANGE_HIGH = 1.33

UNIT_WEIGHTS = {
    "soldiers": 1,
    "tanks": 40,
    "artillery": 30,
    "sam_batteries": 35,
    "fighters": 60,
    "bombers": 70,
    "apaches": 50,
    "destroyers": 120,
    "cruisers": 200,
    "submarines": 150,
    "aircraft_carriers": 250,
    "spies": 0,
    "counter_intel_agents": 0,
    "kamikaze_drones": 5,
    "cruise_missiles": 100,
    "icbms": 500,
    "nukes": 2000,
}


def unit_weight_case_sql(name_expr: str = "LOWER(ud.name)") -> str:
    """SQL CASE giving each unit its combat-accounting weight from UNIT_WEIGHTS."""
    whens = " ".join(
        f"WHEN '{name}' THEN {int(w)}" for name, w in UNIT_WEIGHTS.items() if w
    )
    return f"CASE {name_expr} {whens} ELSE 0 END"


def war_strength(population: int | float | None, military_units: dict | None = None) -> float:
    """Calculate war-range strength from population alone.

    Standing units can be bought or sold before a declaration, letting players
    manipulate matchups. Military remains decisive in combat, but not in
    target eligibility. ``military_units`` stays for caller compatibility.
    """
    return float(population or 0) / 1000.0


def in_war_range(attacker_strength: float, defender_strength: float) -> bool:
    """Check if defender is within attacker's valid war range (75% to 133%)."""
    if attacker_strength <= 0:
        return defender_strength <= 0
    min_range = attacker_strength * WAR_RANGE_LOW
    max_range = attacker_strength * WAR_RANGE_HIGH
    return min_range <= defender_strength <= max_range


def war_range_bounds(attacker_strength: float) -> tuple[float, float]:
    """Return (min_strength, max_strength) bounds for an attacker."""
    return attacker_strength * WAR_RANGE_LOW, attacker_strength * WAR_RANGE_HIGH


def format_war_range_error(attacker_strength: float) -> str:
    """Return the player-facing error string when a target is out of range."""
    min_s, max_s = war_range_bounds(attacker_strength)
    return (
        f"That nation is outside your war range (strength {min_s:,.1f}–{max_s:,.1f}). "
        f"Your strength: {attacker_strength:,.1f}."
    )


def get_user_war_strength(db, user_id: int) -> float:
    """Fetch population-based war-range strength for a nation."""
    db.execute(
        "SELECT COALESCE(SUM(population), 0) FROM provinces WHERE userid = %s",
        (user_id,),
    )
    row = db.fetchone()
    return war_strength(row[0] if row else 0)
