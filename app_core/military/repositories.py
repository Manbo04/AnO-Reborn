from psycopg2.extras import execute_batch
from helpers import get_date

ALL_UNITS = [
    "soldiers",
    "tanks",
    "artillery",
    "bombers",
    "fighters",
    "apaches",
    "destroyers",
    "cruisers",
    "submarines",
    "spies",
    "icbms",
    "nukes",
]

def get_user_units_with_stats(db, cId):
    """Get user units with combat stats and maintenance costs."""
    db.execute(
        """
        SELECT
            ud.name,
            COALESCE(um.quantity, 0) AS quantity,
            ud.base_attack,
            ud.base_defense,
            rd.name AS maintenance_resource,
            ud.maintenance_cost_amount
        FROM unit_dictionary ud
        LEFT JOIN user_military um
            ON um.unit_id = ud.unit_id AND um.user_id = %s
        LEFT JOIN resource_dictionary rd
            ON rd.resource_id = ud.maintenance_cost_resource_id
        WHERE ud.is_active = TRUE
        ORDER BY ud.name
        """,
        (cId,),
    )
    units_list = []
    units_dict = {}
    for row in db.fetchall():
        name, qty, attack, defense, maint_resource, maint_amount = row
        qty = int(qty or 0)
        attack = float(attack or 0)
        defense = float(defense or 0)
        maint_amount = int(maint_amount or 0)
        maint_cost_per_tick = qty * maint_amount

        unit_info = {
            "name": name,
            "quantity": qty,
            "attack": attack,
            "defense": defense,
            "maintenance_resource": maint_resource,
            "maintenance_per_unit": maint_amount,
            "maintenance_per_tick": maint_cost_per_tick,
        }
        units_dict[name] = unit_info
        if qty > 0:
            units_list.append(unit_info)

    # Ensure all units exist in dict with 0 quantity
    for unit in ALL_UNITS:
        if unit not in units_dict:
            units_dict[unit] = {
                "name": unit,
                "quantity": 0,
                "attack": 0,
                "defense": 0,
                "maintenance_resource": None,
                "maintenance_per_unit": 0,
                "maintenance_per_tick": 0,
            }

    return units_dict, units_list


def get_unit_costs(db, unit_name, mildict):
    db.execute(
        """
        SELECT
            unit_id,
            COALESCE(manpower_required, 0) AS manpower_required,
            COALESCE(production_cost_rations, 0) AS production_cost_rations,
            COALESCE(production_cost_components, 0) AS production_cost_components,
            COALESCE(production_cost_steel, 0) AS production_cost_steel,
            COALESCE(production_cost_fuel, 0) AS production_cost_fuel
        FROM unit_dictionary
        WHERE name=%s AND is_active=TRUE
        """,
        (unit_name,),
    )
    row = db.fetchone()
    if not row:
        return None

    (
        unit_id,
        manpower_required,
        cost_rations,
        cost_components,
        cost_steel,
        cost_fuel,
    ) = row
    costs = {
        "rations": int(cost_rations or 0),
        "components": int(cost_components or 0),
        "steel": int(cost_steel or 0),
        "gasoline": int(cost_fuel or 0),
    }
    costs = {k: v for k, v in costs.items() if v > 0}

    # Gold cost is currently sourced from MILDICT until dedicated DB column exists.
    gold_cost = int(mildict.get(unit_name, {}).get("price", 0) or 0)
    manpower_cost = int(
        manpower_required or mildict.get(unit_name, {}).get("manpower", 0) or 0
    )

    return {
        "unit_id": int(unit_id),
        "gold_cost": gold_cost,
        "resource_costs": costs,
        "manpower_cost": manpower_cost,
    }

def get_resource_balances(db, cId, resource_names):
    """Batch fetch all resource balances in a single query."""
    if not resource_names:
        return {}
    db.execute(
        """
        SELECT rd.name, COALESCE(ue.quantity, 0)
        FROM resource_dictionary rd
        LEFT JOIN user_economy ue
            ON ue.resource_id = rd.resource_id AND ue.user_id = %s
        WHERE rd.name = ANY(%s) AND rd.is_active=TRUE
        """,
        (cId, list(resource_names)),
    )
    return {row[0]: int(row[1] or 0) for row in db.fetchall()}

def adjust_resources_batch(db, cId, resource_deltas):
    """Batch adjust multiple resources in 2 queries instead of 2*N."""
    if not resource_deltas:
        return
    names = list(resource_deltas.keys())
    # Ensure rows exist
    execute_batch(
        db,
        """
        INSERT INTO user_economy (user_id, resource_id, quantity)
        SELECT %s, rd.resource_id, 0
        FROM resource_dictionary rd
        WHERE rd.name=%s AND rd.is_active=TRUE
        ON CONFLICT (user_id, resource_id) DO NOTHING
        """,
        [(cId, name) for name in names],
    )
    # Apply deltas
    execute_batch(
        db,
        """
        UPDATE user_economy ue
        SET quantity = GREATEST(0, ue.quantity + %s)
        FROM resource_dictionary rd
        WHERE ue.user_id=%s
          AND ue.resource_id = rd.resource_id
          AND rd.name=%s
          AND rd.is_active=TRUE
        """,
        [(delta, cId, name) for name, delta in resource_deltas.items()],
    )

def get_building_counts(db, cId):
    db.execute(
        """
        SELECT
            COALESCE(
                SUM(CASE WHEN bd.name='army_bases' THEN ub.quantity ELSE 0 END),
                0
            ) AS army_bases,
            COALESCE(
                SUM(CASE WHEN bd.name='harbours' THEN ub.quantity ELSE 0 END),
                0
            ) AS harbours,
            COALESCE(
                SUM(CASE WHEN bd.name='aerodomes' THEN ub.quantity ELSE 0 END),
                0
            ) AS aerodomes,
            COALESCE(
                SUM(
                    CASE WHEN bd.name='admin_buildings' THEN ub.quantity ELSE 0 END
                ),
                0
            ) AS admin_buildings,
            COALESCE(
                SUM(CASE WHEN bd.name='silos' THEN ub.quantity ELSE 0 END),
                0
            ) AS silos
        FROM user_buildings ub
        JOIN building_dictionary bd ON bd.building_id = ub.building_id
        WHERE ub.user_id=%s
        """,
        (cId,)
    )
    return db.fetchone()

def get_manpower_and_gold(db, cId):
    db.execute("SELECT COALESCE(manpower, 0), COALESCE(gold, 0) FROM stats WHERE id=%s", (cId,))
    row = db.fetchone()
    if row:
        return int(row[0] or 0), int(row[1] or 0)
    return 0, 0

def get_current_unit_quantity(db, cId, unit_id):
    db.execute(
        "SELECT COALESCE(quantity, 0) "
        "FROM user_military WHERE user_id=%s AND unit_id=%s",
        (cId, unit_id),
    )
    current_row = db.fetchone()
    return int(current_row[0] or 0) if current_row else 0

def remove_units(db, cId, unit_id, amount):
    db.execute(
        "UPDATE user_military SET quantity = quantity - %s "
        "WHERE user_id=%s AND unit_id=%s",
        (amount, cId, unit_id),
    )

def add_units(db, cId, unit_id, amount):
    db.execute(
        """
        INSERT INTO user_military (user_id, unit_id, quantity)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id, unit_id)
        DO UPDATE SET quantity = user_military.quantity + EXCLUDED.quantity
        """,
        (cId, unit_id, amount),
    )

def update_manpower_and_gold(db, cId, gold_delta, manpower_delta):
    db.execute(
        "UPDATE stats SET gold = GREATEST(0, gold + %s), manpower = GREATEST(0, manpower + %s) WHERE id=%s",
        (gold_delta, manpower_delta, cId),
    )

def insert_revenue(db, cId, rev_type, name, description, units, wantedUnits):
    db.execute(
        (
            "INSERT INTO revenue (user_id, type, name, description, "
            "date, resource, amount) VALUES (%s, %s, %s, %s, %s, %s, %s)"
        ),
        (
            cId,
            rev_type,
            name,
            description,
            get_date(),
            units,
            wantedUnits,
        ),
    )
