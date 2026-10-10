from helpers import get_influence
from database import get_request_cursor


def target_data(cId):
    from wars.war_range import get_user_war_strength, war_range_bounds

    with get_request_cursor() as db:
        strength = get_user_war_strength(db, cId)
    lower, upper = war_range_bounds(strength)
    return {
        "strength": strength,
        "lower": lower,
        "upper": upper,
        "province_range": 0,
    }


def apply_building_damage(db, target_id, building_name, damage_points, threshold):
    """Roll accumulated damage_points against a building_dictionary row the
    defender owns, destroying floor(damage_points // threshold) of them.

    Shared by strategic_airstrike's silo branch's sibling routes
    (drone_strike, cruise_missile_strike in wars/routes.py) so the "N damage
    points needed to destroy 1 X" mechanic lives in one place instead of
    being copy-pasted per weapon type. Returns (destroyed_count, had_any)
    where had_any is False if the defender owns none of building_name at all
    (distinguishes "nothing to destroy" from "destroyed 0, missed").
    """
    # user_buildings has one row per (user, building, province). Spread the
    # destruction over those rows, biggest stack first; a single unfiltered
    # UPDATE would subtract from every province and trip the quantity >= 0
    # check (the 500 Kaiser hit launching drones/missiles 2026-10-08).
    db.execute(
        """
        SELECT ub.province_id, ub.quantity, ub.building_id
        FROM user_buildings ub
        JOIN building_dictionary bd ON bd.building_id = ub.building_id
        WHERE ub.user_id = %s AND bd.name = %s AND ub.quantity > 0
        ORDER BY ub.quantity DESC, ub.province_id
        FOR UPDATE OF ub
        """,
        (target_id, building_name),
    )
    rows = db.fetchall()
    total = sum(int(r[1]) for r in rows)
    if total <= 0:
        return 0, False

    destroyed = min(total, int(damage_points // threshold))
    left = destroyed
    for province_id, quantity, building_id in rows:
        if left <= 0:
            break
        take = min(int(quantity), left)
        if province_id is None:
            db.execute(
                "UPDATE user_buildings SET quantity = quantity - %s "
                "WHERE user_id = %s AND building_id = %s AND province_id IS NULL",
                (take, target_id, building_id),
            )
        else:
            db.execute(
                "UPDATE user_buildings SET quantity = quantity - %s "
                "WHERE user_id = %s AND building_id = %s AND province_id = %s",
                (take, target_id, building_id, province_id),
            )
        left -= take
    return destroyed, True


# Business logic for war mechanics will be moved here


def apply_population_strike(db, target_id, kill_frac):
    """Kill kill_frac of the target's most populous province (drone/cruise
    missile "population" target, The_kaiser's request 2026-10-04).

    Same update shape as wars/nuclear.py: only `population` is changed for the
    age split (trg_sync_province_population rescales children/working/elderly),
    the education split is scaled here. Returns (province_name, deaths,
    happiness_lost) or None if the target has no populated province.
    """
    db.execute(
        """
        SELECT id, provincename, COALESCE(population, 0)
        FROM provinces WHERE userid = %s AND COALESCE(population, 0) > 0
        ORDER BY population DESC LIMIT 1 FOR UPDATE
        """,
        (target_id,),
    )
    row = db.fetchone()
    if not row:
        return None
    province_id, province_name, pop = row[0], row[1], int(row[2])
    deaths = int(pop * kill_frac)
    if deaths <= 0:
        return province_name, 0, 0
    survive = 1.0 - deaths / pop
    # 2% killed (the per-strike cap) costs 10 happiness.
    happiness_lost = max(1, min(10, round(kill_frac * 500)))
    db.execute(
        """
        UPDATE provinces SET
            population = GREATEST(0, population - %s),
            edu_none = FLOOR(COALESCE(edu_none, 0) * %s),
            edu_highschool = FLOOR(COALESCE(edu_highschool, 0) * %s),
            edu_college = FLOOR(COALESCE(edu_college, 0) * %s),
            happiness = GREATEST(0, COALESCE(happiness, 0) - %s)
        WHERE id = %s
        """,
        (deaths, survive, survive, survive, happiness_lost, province_id),
    )
    return province_name, deaths, happiness_lost
