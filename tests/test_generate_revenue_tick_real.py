"""The hourly production tick (generate_province_revenue), real schema.

This tick silently produced nothing for ~12h on 2026-10-03 (a query read a
column that does not exist; b027fdab). Replaces test_generate_revenue_mock,
whose fake cursor no longer matched the tick's queries.
  * one run makes a farming province produce rations,
  * an immediate rerun produces nothing more (task_runs gate).
"""
import uuid

import pytest

from database import get_db_connection
from tests._db_cleanup import purge_users

pytestmark = pytest.mark.no_server


def _rations(db, uid):
    db.execute(
        "SELECT COALESCE(SUM(ue.quantity), 0) FROM user_economy ue "
        "JOIN resource_dictionary rd ON rd.resource_id = ue.resource_id "
        "WHERE ue.user_id = %s AND rd.name = 'rations'",
        (uid,),
    )
    return int(db.fetchone()[0])


@pytest.fixture
def farming_nation():
    name = f"rev_{uuid.uuid4().hex[:8]}"
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            "INSERT INTO users (username, email, date, hash, auth_type) "
            "VALUES (%s, %s, '2026-10-06', 'x', 'normal') RETURNING id",
            (name, f"{name}@example.invalid"),
        )
        uid = db.fetchone()[0]
        db.execute(
            "INSERT INTO stats (id, location, gold) VALUES (%s, 'Grassland', 100000000)", (uid,)
        )
        db.execute(
            "INSERT INTO provinces (userid, provincename, citycount, land, population, "
            "happiness, productivity, energy, pop_children, pop_working, pop_elderly, "
            "edu_none) VALUES (%s, %s, 10, 50, 5000000, 80, 80, 100, 1000000, 3000000, "
            "1000000, 3000000) RETURNING id",
            (uid, f"{name}-farm"),
        )
        pid = db.fetchone()[0]
        db.execute(
            "INSERT INTO user_buildings (user_id, building_id, province_id, quantity) "
            "SELECT %s, building_id, %s, 10 FROM building_dictionary WHERE name = 'farms'",
            (uid, pid),
        )
        db.execute("DELETE FROM task_runs WHERE task_name = 'generate_province_revenue'")
        conn.commit()
    yield uid
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("DELETE FROM task_runs WHERE task_name = 'generate_province_revenue'")
        db.execute("DELETE FROM user_buildings WHERE user_id = %s", (uid,))
        db.execute("DELETE FROM user_economy WHERE user_id = %s", (uid,))
        db.execute("DELETE FROM provinces WHERE userid = %s", (uid,))
        purge_users(db, [uid])
        conn.commit()


def test_production_tick_produces_and_gates_reruns(farming_nation):
    from app_core.game_ticks.revenue import generate_province_revenue

    with get_db_connection() as conn:
        before = _rations(conn.cursor(), farming_nation)

    generate_province_revenue()
    with get_db_connection() as conn:
        after_first = _rations(conn.cursor(), farming_nation)
    assert after_first > before, "farms produced no rations"

    generate_province_revenue()
    with get_db_connection() as conn:
        assert _rations(conn.cursor(), farming_nation) == after_first
