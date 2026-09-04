"""Hourly tick: drone_sites/missile_batteries manufacture units into a
per-user stockpile (app_core/military/services.py::process_activate_units
later moves stockpile -> user_military for a gold-only price).

Deliberately a standalone tick with its own advisory lock and task_runs row,
rather than folded into generate_province_revenue()'s resource-production
loop -- that loop only ever writes to user_economy (a resource), and
threading a second output type (a capped-per-building unit stockpile)
through its ~1200 lines of shared state was a lot more risk for this feature
than a small dedicated pass. See variables.UNIT_STOCKPILE_BUILDINGS for the
per-building unit/cap/resource-cost config this reads.
"""
from psycopg2.extras import execute_batch

import variables
from app_core.game_ticks.common import should_skip_task, handle_exception, log_verbose
from app_core.game_ticks.locks import try_pg_advisory_lock, release_pg_advisory_lock

TASK_NAME = "produce_unit_stockpiles"
ADVISORY_LOCK_ID = 9011


def produce_unit_stockpiles():
    from database import get_db_connection

    with get_db_connection() as conn:
        if not try_pg_advisory_lock(conn, ADVISORY_LOCK_ID, TASK_NAME):
            return

        try:
            db = conn.cursor()
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS task_runs (
                    task_name TEXT PRIMARY KEY,
                    last_run TIMESTAMP WITH TIME ZONE
                )
                """
            )
            db.execute(
                "INSERT INTO task_runs (task_name, last_run) VALUES (%s, NULL) "
                "ON CONFLICT DO NOTHING",
                (TASK_NAME,),
            )
            db.execute(
                "SELECT last_run FROM task_runs WHERE task_name=%s FOR UPDATE",
                (TASK_NAME,),
            )
            row = db.fetchone()
            if should_skip_task(row, TASK_NAME):
                return

            for building_name, spec in variables.UNIT_STOCKPILE_BUILDINGS.items():
                _produce_for_building(db, building_name, spec)

            db.execute(
                "UPDATE task_runs SET last_run = now() WHERE task_name=%s",
                (TASK_NAME,),
            )
        except Exception as e:
            handle_exception(e, TASK_NAME)
            raise
        finally:
            try:
                release_pg_advisory_lock(conn, ADVISORY_LOCK_ID)
            except Exception:
                pass


def _produce_for_building(db, building_name, spec):
    unit_name = spec["unit"]
    cap_per_building = spec["cap_per_building"]
    per_tick = spec["production_per_tick"]
    resource_cost = spec["resource_cost"]

    # Owners of at least one of this building, total count across every
    # province they own -- the stockpile/cap is per-user (like user_military
    # itself), not per-province.
    db.execute(
        """
        SELECT ub.user_id, SUM(ub.quantity)
        FROM user_buildings ub
        JOIN building_dictionary bd ON bd.building_id = ub.building_id
        WHERE bd.name = %s
        GROUP BY ub.user_id
        HAVING SUM(ub.quantity) > 0
        """,
        (building_name,),
    )
    owners = db.fetchall()
    if not owners:
        return

    site_counts = {row[0]: int(row[1]) for row in owners}
    user_ids = list(site_counts.keys())

    db.execute(
        "SELECT unit_id FROM unit_dictionary WHERE name=%s AND is_active=TRUE",
        (unit_name,),
    )
    unit_row = db.fetchone()
    if not unit_row:
        log_verbose(f"UNIT_PRODUCTION | {building_name}: unit '{unit_name}' not found")
        return
    unit_id = unit_row[0]

    db.execute(
        "SELECT user_id, quantity FROM user_unit_stockpile "
        "WHERE unit_id=%s AND user_id = ANY(%s)",
        (unit_id, user_ids),
    )
    current_stockpile = {row[0]: int(row[1]) for row in db.fetchall()}

    resource_names = list(resource_cost.keys())
    db.execute(
        """
        SELECT ue.user_id, rd.name, ue.quantity
        FROM user_economy ue
        JOIN resource_dictionary rd ON rd.resource_id = ue.resource_id
        WHERE rd.name = ANY(%s) AND ue.user_id = ANY(%s)
        """,
        (resource_names, user_ids),
    )
    balances = {}
    for uid, rname, qty in db.fetchall():
        balances.setdefault(uid, {})[rname] = int(qty)

    stockpile_updates = []  # (user_id, unit_id, amount)
    resource_deltas = {}  # user_id -> {resource_name: -amount}

    for user_id in user_ids:
        cap = site_counts[user_id] * cap_per_building
        headroom = max(0, cap - current_stockpile.get(user_id, 0))
        if headroom <= 0:
            continue

        desired = min(site_counts[user_id] * per_tick, headroom)

        user_balances = balances.get(user_id, {})
        affordable = desired
        for resource, amount_per_unit in resource_cost.items():
            if amount_per_unit <= 0:
                continue
            affordable = min(affordable, user_balances.get(resource, 0) // amount_per_unit)

        if affordable <= 0:
            log_verbose(
                f"F | UNIT_PRODUCTION | USER: {user_id} | {building_name} "
                f"({site_counts[user_id]}) | not enough resources for {unit_name}"
            )
            continue

        if affordable < desired:
            log_verbose(
                f"P | UNIT_PRODUCTION | USER: {user_id} | {building_name} | "
                f"partial -- {affordable}/{desired} {unit_name}"
            )

        stockpile_updates.append((user_id, unit_id, affordable))
        deltas = resource_deltas.setdefault(user_id, {})
        for resource, amount_per_unit in resource_cost.items():
            deltas[resource] = deltas.get(resource, 0) - amount_per_unit * affordable

    if stockpile_updates:
        execute_batch(
            db,
            """
            INSERT INTO user_unit_stockpile (user_id, unit_id, quantity)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, unit_id)
            DO UPDATE SET quantity = user_unit_stockpile.quantity + EXCLUDED.quantity,
                          updated_at = now()
            """,
            stockpile_updates,
        )

    if resource_deltas:
        db.execute(
            "SELECT name, resource_id FROM resource_dictionary WHERE name = ANY(%s)",
            (resource_names,),
        )
        resource_id_map = {row[0]: row[1] for row in db.fetchall()}

        ensure_rows = []
        apply_deltas = []
        for user_id, deltas in resource_deltas.items():
            for rname, delta in deltas.items():
                rid = resource_id_map.get(rname)
                if not rid or delta == 0:
                    continue
                ensure_rows.append((user_id, rid))
                apply_deltas.append((delta, user_id, rid))

        if ensure_rows:
            execute_batch(
                db,
                """
                INSERT INTO user_economy (user_id, resource_id, quantity)
                VALUES (%s, %s, 0)
                ON CONFLICT (user_id, resource_id) DO NOTHING
                """,
                ensure_rows,
            )
        if apply_deltas:
            execute_batch(
                db,
                """
                UPDATE user_economy
                SET quantity = GREATEST(0, quantity + %s), updated_at = now()
                WHERE user_id=%s AND resource_id=%s
                """,
                apply_deltas,
            )
