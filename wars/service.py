from helpers import get_influence


def target_data(cId):
    from database import get_db_cursor

    with get_db_cursor() as db:
        influence = get_influence(cId)
        db.execute("SELECT COUNT(id) FROM provinces WHERE userid=(%s)", (cId,))
        province_range = db.fetchone()[0]
    data = {
        "upper": influence * 2,
        "lower": influence * 0.9,
        "province_range": province_range,
    }
    return data


from database import get_db_cursor
from attack_scripts import Nation
import time


def update_supply(war_id):
    MAX_SUPPLY = 2000
    with get_db_cursor() as db:
        db.execute(
            "SELECT attacker_supplies,defender_supplies,last_visited FROM wars WHERE id=%s",
            (war_id,),
        )
        attacker_supplies, defender_supplies, supply_date = db.fetchall()[0]
        current_time = time.time()
        if current_time < int(supply_date):
            return "TIME STAMP IS CORRUPTED"
        time_difference = current_time - supply_date
        hours_count = time_difference // 3600
        supply_by_hours = hours_count * 50  # 50 supply in every hour
        if supply_by_hours > 0:
            db.execute("SELECT attacker,defender FROM wars where id=(%s)", (war_id,))
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
                "UPDATE wars SET last_visited=(%s) WHERE id=(%s)", (time.time(), war_id)
            )


# Business logic for war mechanics will be moved here
