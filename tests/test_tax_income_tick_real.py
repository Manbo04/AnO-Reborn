"""The hourly tax tick (tax_income) against the real schema.

Replaces three fake-cursor tests (test_tax_income_flow_mock,
test_tax_income_locking, test_resources_flow's CG clamp) that modelled an
older shape of the tick. Checks what players care about:
  * one run pays gold and consumes consumer goods,
  * an immediate second run pays nothing (task_runs gate),
  * two concurrent runs pay exactly once (advisory lock).
"""
import threading
import uuid

import pytest

from database import get_db_connection
from tests._db_cleanup import purge_users

CG_STOCK = 10**9


def _cg(db, uid):
    db.execute(
        "SELECT COALESCE(ue.quantity, 0) FROM user_economy ue "
        "JOIN resource_dictionary rd ON rd.resource_id = ue.resource_id "
        "WHERE ue.user_id = %s AND rd.name = 'consumer_goods'",
        (uid,),
    )
    row = db.fetchone()
    return int(row[0]) if row else 0


def _gold(db, uid):
    db.execute("SELECT gold FROM stats WHERE id = %s", (uid,))
    return int(db.fetchone()[0])


def _reset_tick(db, uid):
    db.execute("DELETE FROM task_runs WHERE task_name = 'tax_income'")
    db.execute("DELETE FROM task_cursors WHERE task_name = 'tax_income'")
    db.execute("UPDATE stats SET gold = 0 WHERE id = %s", (uid,))
    db.execute(
        "UPDATE user_economy ue SET quantity = %s FROM resource_dictionary rd "
        "WHERE rd.resource_id = ue.resource_id AND rd.name = 'consumer_goods' "
        "AND ue.user_id = %s",
        (CG_STOCK, uid),
    )


@pytest.fixture
def nation():
    import variables

    retail = next(iter(variables.CONSUMER_GOODS_DISTRIBUTION_PER_BUILDING))
    name = f"tick_{uuid.uuid4().hex[:8]}"
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            "INSERT INTO users (username, email, date, hash, auth_type) "
            "VALUES (%s, %s, '2026-10-06', 'x', 'normal') RETURNING id",
            (name, f"{name}@example.invalid"),
        )
        uid = db.fetchone()[0]
        db.execute("INSERT INTO stats (id, location, gold) VALUES (%s, 'Grassland', 0)", (uid,))
        db.execute(
            "INSERT INTO provinces (userid, provincename, citycount, land, population, "
            "happiness, productivity, pop_children, pop_working, pop_elderly) "
            "VALUES (%s, %s, 5, 10, 1000000, 60, 60, 200000, 600000, 200000) RETURNING id",
            (uid, f"{name}-core"),
        )
        pid = db.fetchone()[0]
        db.execute(
            "INSERT INTO user_buildings (user_id, building_id, province_id, quantity) "
            "SELECT %s, building_id, %s, 1000 FROM building_dictionary WHERE name = %s",
            (uid, pid, retail),
        )
        db.execute(
            "INSERT INTO user_economy (user_id, resource_id, quantity) "
            "SELECT %s, resource_id, %s FROM resource_dictionary WHERE name = 'consumer_goods'",
            (uid, CG_STOCK),
        )
        _reset_tick(db, uid)
        conn.commit()
    yield uid
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("DELETE FROM task_runs WHERE task_name = 'tax_income'")
        db.execute("DELETE FROM task_cursors WHERE task_name = 'tax_income'")
        db.execute("DELETE FROM provinces WHERE userid = %s", (uid,))
        db.execute("DELETE FROM user_buildings WHERE user_id = %s", (uid,))
        db.execute("DELETE FROM user_economy WHERE user_id = %s", (uid,))
        purge_users(db, [uid])
        conn.commit()


def _run_tick():
    from app_core.game_ticks.taxes import tax_income

    tax_income()


@pytest.mark.no_server
def test_tax_tick_pays_once_and_gates_reruns(nation):
    from app_core.game_ticks.taxes import calc_ti

    expected_income, expected_cg = calc_ti(nation)
    assert expected_income > 0 and expected_cg > 0

    _run_tick()
    with get_db_connection() as conn:
        db = conn.cursor()
        paid = _gold(db, nation)
        consumed = CG_STOCK - _cg(db, nation)
    assert paid > 0
    assert consumed == expected_cg

    _run_tick()  # immediately again: the task_runs gate must skip it
    with get_db_connection() as conn:
        db = conn.cursor()
        assert _gold(db, nation) == paid
        assert CG_STOCK - _cg(db, nation) == consumed


@pytest.mark.no_server
def test_two_concurrent_tax_ticks_pay_exactly_once(nation):
    _run_tick()
    with get_db_connection() as conn:
        db = conn.cursor()
        single = _gold(db, nation)
        _reset_tick(db, nation)
        conn.commit()

    barrier = threading.Barrier(2)
    errors = []

    def _racer():
        try:
            barrier.wait(timeout=5)
            _run_tick()
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=_racer) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert not errors, errors
    with get_db_connection() as conn:
        db = conn.cursor()
        assert _gold(db, nation) == single
