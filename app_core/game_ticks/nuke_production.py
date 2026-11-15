"""Hourly tick: Nuclear Weapons Facilities manufacture nukes (flag nuke_rework).

Each facility adds 1/72 of a nuke per hour to user_nuke_progress. Whole nukes
are produced only while (owned + stockpiled) < silo capacity and the nation can
pay the per-unit resources; otherwise progress waits at 1.0 (no banking).
Optional auto-activation spends the activation gold. Own advisory lock + task_runs.
"""
import logging
from decimal import Decimal

import variables
from app_core import nuke_rework as nr
from app_core.economy import ledger
from app_core.game_ticks.common import handle_exception, should_skip_task
from app_core.game_ticks.locks import release_pg_advisory_lock, try_pg_advisory_lock

logger = logging.getLogger(__name__)
TASK_NAME = "produce_nukes"
ADVISORY_LOCK_ID = 9012


def produce_nukes():
    if not nr.enabled():
        return
    from database import get_db_connection

    with get_db_connection() as conn:
        if not try_pg_advisory_lock(conn, ADVISORY_LOCK_ID, TASK_NAME):
            return
        try:
            db = conn.cursor()
            db.execute(
                "CREATE TABLE IF NOT EXISTS task_runs (task_name TEXT PRIMARY KEY, last_run TIMESTAMP WITH TIME ZONE)"
            )
            db.execute(
                "INSERT INTO task_runs (task_name, last_run) VALUES (%s, NULL) ON CONFLICT DO NOTHING",
                (TASK_NAME,),
            )
            db.execute("SELECT last_run FROM task_runs WHERE task_name=%s FOR UPDATE", (TASK_NAME,))
            if should_skip_task(db.fetchone(), TASK_NAME, db=db):
                return
            _produce(db)
            db.execute("UPDATE task_runs SET last_run = now() WHERE task_name=%s", (TASK_NAME,))
        except Exception as e:
            handle_exception(e, TASK_NAME)
            raise
        finally:
            try:
                release_pg_advisory_lock(conn, ADVISORY_LOCK_ID)
            except Exception:
                pass


def _produce(db):
    db.execute(
        "SELECT ub.user_id, SUM(ub.quantity) FROM user_buildings ub "
        "JOIN building_dictionary bd ON bd.building_id=ub.building_id "
        "WHERE bd.name=%s GROUP BY ub.user_id HAVING SUM(ub.quantity) > 0",
        (nr.FACILITY,),
    )
    owners = [(r[0], int(r[1])) for r in db.fetchall()]
    if not owners:
        return
    db.execute("SELECT unit_id FROM unit_dictionary WHERE name=%s", (nr.UNIT,))
    row = db.fetchone()
    if not row:
        return
    unit_id = row[0]
    db.execute("SELECT name, resource_id FROM resource_dictionary WHERE name = ANY(%s)", (list(nr.MISSILE_RESOURCES),))
    rid = {r[0]: r[1] for r in db.fetchall()}
    for user_id, facilities in owners:
        try:
            produce_for_user(db, user_id, facilities, unit_id, rid)
        except Exception:
            logger.exception("nuke production failed for user %s", user_id)


def produce_for_user(db, user_id, facilities, unit_id, rid):
    """One hourly step for one nation. Returns number of nukes manufactured."""
    db.execute("SELECT progress FROM user_nuke_progress WHERE user_id=%s FOR UPDATE", (user_id,))
    r = db.fetchone()
    progress = Decimal(r[0]) if r else Decimal(0)
    progress += Decimal(facilities) / Decimal(nr.HOURS_PER_MISSILE)

    db.execute("SELECT COALESCE(quantity,0) FROM user_military WHERE user_id=%s AND unit_id=%s", (user_id, unit_id))
    r = db.fetchone()
    owned = int(r[0]) if r else 0
    db.execute("SELECT COALESCE(quantity,0) FROM user_unit_stockpile WHERE user_id=%s AND unit_id=%s", (user_id, unit_id))
    r = db.fetchone()
    stocked = int(r[0]) if r else 0
    room = max(0, nr.capacity(db, user_id) - owned - stocked)

    made = min(int(progress), room)
    if made > 0:
        db.execute(
            "SELECT rd.name, COALESCE(ue.quantity,0) FROM resource_dictionary rd "
            "LEFT JOIN user_economy ue ON ue.resource_id=rd.resource_id AND ue.user_id=%s "
            "WHERE rd.name = ANY(%s)",
            (user_id, list(nr.MISSILE_RESOURCES)),
        )
        have = {n: int(q or 0) for n, q in db.fetchall()}
        for res, per in nr.MISSILE_RESOURCES.items():
            made = min(made, have.get(res, 0) // per)
    if made > 0:
        ledger.ensure_resource_rows_batch(db, [(user_id, rid[res]) for res in nr.MISSILE_RESOURCES])
        ledger.adjust_resource_batch(db, [(user_id, rid[res], -per * made) for res, per in nr.MISSILE_RESOURCES.items()])
        db.execute(
            "INSERT INTO user_unit_stockpile (user_id, unit_id, quantity) VALUES (%s,%s,%s) "
            "ON CONFLICT (user_id, unit_id) DO UPDATE SET quantity = user_unit_stockpile.quantity + EXCLUDED.quantity, updated_at=now()",
            (user_id, unit_id, made),
        )
        progress -= made
    progress = min(progress, Decimal(1))  # no banking beyond one pending unit
    db.execute(
        "INSERT INTO user_nuke_progress (user_id, progress) VALUES (%s,%s) "
        "ON CONFLICT (user_id) DO UPDATE SET progress=EXCLUDED.progress, updated_at=now()",
        (user_id, progress),
    )
    if made > 0:
        _auto_activate(db, user_id)
    return made


def _auto_activate(db, user_id):
    db.execute("SELECT auto_missile FROM user_nuke_settings WHERE user_id=%s", (user_id,))
    r = db.fetchone()
    if not r or not r[0]:
        return
    from app_core.military.repositories import get_stockpile_quantity
    from app_core.military.services import process_activate_units

    db.execute("SELECT unit_id FROM unit_dictionary WHERE name=%s", (nr.UNIT,))
    n = get_stockpile_quantity(db, user_id, db.fetchone()[0])
    price = int(variables.MILDICT[nr.UNIT]["price"])
    db.execute("SELECT gold FROM stats WHERE id=%s", (user_id,))
    gold = int(db.fetchone()[0] or 0)
    n = min(n, gold // price if price else n)
    if n > 0:
        process_activate_units(db, user_id, nr.UNIT, n, variables.MILDICT)
