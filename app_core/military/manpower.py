"""Pure logic and database helpers for army manpower caps tied to working population.

Rule B4: Each military unit requires crew/manpower. Total manpower of ALL units
the nation owns may not exceed MANPOWER_SHARE = 10% of working-age population
(pop_working summed over provinces; fallback to population if absent).
"""

# Crew per unit = the same per-unit manpower the recruitment pool already
# charges (variables.MILDICT "manpower"), so both systems agree. Missiles,
# nukes and drones have none.
def _crew_table() -> dict:
    from variables import MILDICT

    return {
        name: int(spec.get("manpower", 0) or 0)
        for name, spec in MILDICT.items()
        if isinstance(spec, dict)
    }


UNIT_MANPOWER_CREW = _crew_table()

MANPOWER_SHARE = 0.10


def unit_crew_requirement(unit_name: str) -> int:
    """Return crew / manpower needed per unit."""
    return UNIT_MANPOWER_CREW.get(unit_name, 0)


def calc_manpower_cap(pop_working: int, population: int = 0) -> int:
    """Calculate the maximum manpower allowed for a nation.

    Cap = MANPOWER_SHARE (10%) of the nation's working-age population
    (pop_working summed over provinces; fall back to population if absent or 0).
    """
    effective_pop = int(pop_working or 0)
    if effective_pop <= 0:
        effective_pop = int(population or 0)
    return max(0, int(effective_pop * MANPOWER_SHARE))


def calc_used_manpower(units: dict) -> int:
    """Calculate total manpower used by all units owned by a nation."""
    total = 0
    for name, val in (units or {}).items():
        if isinstance(val, dict):
            qty = int(val.get("quantity") or 0)
        else:
            qty = int(val or 0)
        if qty > 0:
            total += qty * unit_crew_requirement(name)
    return total


def calc_free_manpower(cap: int, used: int) -> int:
    """Calculate remaining free manpower under the cap."""
    return max(0, int(cap or 0) - int(used or 0))


def can_recruit(
    unit_name: str, count: int, current_used: int, cap: int
) -> tuple[bool, int, int]:
    """Check if recruiting `count` of `unit_name` is within manpower cap.

    Returns:
        (allowed, needed_crew, free_crew)
    """
    needed_crew = int(count or 0) * unit_crew_requirement(unit_name)
    free_crew = calc_free_manpower(cap, current_used)
    allowed = (current_used + needed_crew) <= cap
    return allowed, needed_crew, free_crew


def format_manpower_error(needed_crew: int, free_crew: int) -> str:
    """Error message when recruitment exceeds manpower cap."""
    return (
        f"Not enough manpower: this needs {needed_crew} crew, "
        f"you have {free_crew} free (cap = 10% of working population)."
    )


def get_user_manpower_data(db, user_id: int) -> dict:
    """Fetch manpower cap and used numbers for a user in 2 queries."""
    # Query 1: sum working population (fallback total population) across provinces
    db.execute(
        """
        SELECT
            COALESCE(SUM(pop_working), 0) AS total_working,
            COALESCE(SUM(population), 0) AS total_pop
        FROM provinces
        WHERE userid = %s
        """,
        (user_id,),
    )
    row = db.fetchone()
    if row:
        pop_working = int(row[0] or 0)
        population = int(row[1] or 0)
    else:
        pop_working = 0
        population = 0

    cap = calc_manpower_cap(pop_working, population)

    # Query 2: user military units
    db.execute(
        """
        SELECT
            ud.name,
            COALESCE(um.quantity, 0) AS quantity
        FROM unit_dictionary ud
        LEFT JOIN user_military um
            ON um.unit_id = ud.unit_id AND um.user_id = %s
        WHERE ud.is_active = TRUE
        """,
        (user_id,),
    )
    units = {name: int(qty or 0) for name, qty in db.fetchall()}
    used = calc_used_manpower(units)
    free = calc_free_manpower(cap, used)

    return {
        "cap": cap,
        "used": used,
        "free": free,
        "pop_working": pop_working,
        "population": population,
        "units": units,
    }
