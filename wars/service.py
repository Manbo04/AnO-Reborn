from helpers import get_influence
from database import get_request_cursor
from attack_scripts import Nation
import time


def target_data(cId):
    with get_request_cursor() as db:
        influence = get_influence(cId)
        db.execute("SELECT COUNT(id) FROM provinces WHERE userid=(%s)", (cId,))
        prov_row = db.fetchone()
        province_range = prov_row[0] if prov_row else 0
    data = {
        "upper": influence * 2,
        "lower": influence * 0.9,
        "province_range": province_range,
    }
    return data


def update_supply(war_id):
    MAX_SUPPLY = 2000
    with get_request_cursor() as db:
        db.execute(
            (
                "SELECT attacker_supplies,defender_supplies,last_visited "
                "FROM wars WHERE id=%s"
            ),
            (war_id,),
        )
        war_rows = db.fetchall()
        if not war_rows:
            return
        attacker_supplies, defender_supplies, supply_date = war_rows[0]
        current_time = time.time()
        if current_time < int(supply_date):
            return "TIME STAMP IS CORRUPTED"
        time_difference = current_time - supply_date
        hours_count = time_difference // 3600
        supply_by_hours = hours_count * 50  # 50 supply in every hour
        if supply_by_hours > 0:
            db.execute(
                "SELECT attacker,defender FROM wars where id=(%s)", (war_id,)
            )
            attacker_id, defender_id = db.fetchone()
            attacker_upgrades = Nation.get_upgrades("supplies", attacker_id)
            defender_upgrades = Nation.get_upgrades("supplies", defender_id)
            for i in attacker_upgrades.values():
                attacker_supplies += i
            for i in defender_upgrades.values():
                defender_supplies += i
            if (supply_by_hours + attacker_supplies) > MAX_SUPPLY:
                db.execute(
                    "UPDATE wars SET attacker_supplies=(%s) WHERE id=(%s)",
                    (MAX_SUPPLY, war_id),
                )
            else:
                db.execute(
                    "UPDATE wars SET attacker_supplies=(%s) WHERE id=(%s)",
                    (supply_by_hours + attacker_supplies, war_id),
                )
            if (supply_by_hours + defender_supplies) > MAX_SUPPLY:
                db.execute(
                    "UPDATE wars SET defender_supplies=(%s) WHERE id=(%s)",
                    (MAX_SUPPLY, war_id),
                )
            else:
                db.execute(
                    "UPDATE wars SET defender_supplies=(%s) WHERE id=(%s)",
                    (supply_by_hours + defender_supplies, war_id),
                )
            db.execute(
                ("UPDATE wars SET last_visited=(%s) " "WHERE id=(%s)"),
                (time.time(), war_id),
            )


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
    db.execute(
        """
        SELECT ub.quantity, ub.building_id
        FROM user_buildings ub
        JOIN building_dictionary bd ON bd.building_id = ub.building_id
        WHERE ub.user_id = %s AND bd.name = %s
        """,
        (target_id, building_name),
    )
    row = db.fetchone()
    if not row or row[0] <= 0:
        return 0, False

    count, building_id = row
    destroyed = min(count, int(damage_points // threshold))
    if destroyed > 0:
        db.execute(
            "UPDATE user_buildings SET quantity = quantity - %s WHERE user_id = %s AND building_id = %s",
            (destroyed, target_id, building_id),
        )
    return destroyed, True


# Business logic for war mechanics will be moved here
