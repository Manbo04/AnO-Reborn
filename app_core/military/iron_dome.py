"""Iron Dome province air defense (migration 0104).

Domes are bought per province and only defend the province they sit in.
Nukes target one province, so they face that province's domes. Drone and
cruise-missile strikes hit buildings nationwide, so they face the nation's
average dome coverage per province."""

from .repositories import (
    adjust_resources_batch,
    get_manpower_and_gold,
    get_resource_balances,
    insert_revenue,
    update_manpower_and_gold,
)

MAX_DOMES_PER_PROVINCE = 10
DOME_GOLD_COST = 250_000
DOME_RESOURCE_COSTS = {"components": 6000, "steel": 20000, "aluminium": 8000}
DOME_UPKEEP_GASOLINE = 20  # per dome per military-maintenance tick (hourly)
SELL_REFUND = 0.5  # fraction of gold refunded on dismantle


def province_domes(db, province_id) -> int:
    db.execute(
        "SELECT quantity FROM province_iron_domes WHERE province_id = %s",
        (province_id,),
    )
    row = db.fetchone()
    return int(row[0]) if row else 0


def average_domes(db, user_id) -> float:
    db.execute(
        """
        SELECT COALESCE(SUM(d.quantity), 0), COUNT(p.id)
        FROM provinces p
        LEFT JOIN province_iron_domes d ON d.province_id = p.id
        WHERE p.userid = %s
        """,
        (user_id,),
    )
    total, provinces = db.fetchone()
    return float(total) / provinces if provinces else 0.0


def has_star_wars(db, user_id) -> bool:
    db.execute(
        """
        SELECT 1 FROM user_tech ut
        JOIN tech_dictionary td ON td.tech_id = ut.tech_id
        WHERE ut.user_id = %s AND ut.is_unlocked = TRUE
          AND td.name = 'star_wars_project'
        """,
        (user_id,),
    )
    return bool(db.fetchone())


def roll_intercepts(db, defender_id, count, projectile_type, province_id=None, rng=None):
    """How many of `count` incoming projectiles the defender's domes shoot down."""
    from wars.air_defense import calculate_iron_dome_interception

    if count <= 0:
        return 0
    domes = province_domes(db, province_id) if province_id else average_domes(db, defender_id)
    pct = calculate_iron_dome_interception(
        domes, projectile_type, has_star_wars(db, defender_id), rng=rng
    )
    return min(count, int(round(count * pct)))


def change_domes(db, user_id, province_id, way, amount):
    """Buy or dismantle domes in one of the user's provinces. Returns
    (ok, message)."""
    db.execute("SELECT pg_advisory_xact_lock(%s)", (user_id,))
    db.execute("SELECT userid FROM provinces WHERE id = %s", (province_id,))
    row = db.fetchone()
    if not row:
        return False, "Province doesn't exist"
    if int(row[0]) != int(user_id):
        return False, "You do not own this province"
    if amount <= 0:
        return False, "Amount must be at least 1"

    current = province_domes(db, province_id)
    if way == "buy":
        if current + amount > MAX_DOMES_PER_PROVINCE:
            return False, f"A province can hold at most {MAX_DOMES_PER_PROVINCE} Iron Domes (has {current})"
        _, gold = get_manpower_and_gold(db, user_id)
        gold_cost = DOME_GOLD_COST * amount
        if gold_cost > gold:
            return False, f"Not enough money ({gold}/{gold_cost})"
        balances = get_resource_balances(db, user_id, DOME_RESOURCE_COSTS.keys())
        for res, per in DOME_RESOURCE_COSTS.items():
            need = per * amount
            if balances.get(res, 0) < need:
                return False, f"Not enough {res} ({balances.get(res, 0)}/{need})"
        adjust_resources_batch(db, user_id, {r: -p * amount for r, p in DOME_RESOURCE_COSTS.items()})
        update_manpower_and_gold(db, user_id, gold_delta=-gold_cost, manpower_delta=0)
        insert_revenue(db, user_id, "expense", f"Building {amount} Iron Dome(s).", "", "iron_domes", amount)
        delta = amount
    elif way == "sell":
        if amount > current:
            return False, f"You only have {current} Iron Domes here"
        update_manpower_and_gold(
            db, user_id, gold_delta=int(DOME_GOLD_COST * SELL_REFUND * amount), manpower_delta=0
        )
        delta = -amount
    else:
        return False, "Invalid action"

    db.execute(
        """
        INSERT INTO province_iron_domes (province_id, quantity) VALUES (%s, %s)
        ON CONFLICT (province_id) DO UPDATE
        SET quantity = province_iron_domes.quantity + EXCLUDED.quantity
        """,
        (province_id, delta),
    )
    return True, "Success"
