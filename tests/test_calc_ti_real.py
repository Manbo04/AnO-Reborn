"""calc_ti() (hourly tax income) against the real schema.

Replaces test_calc_ti_mock.py, whose fake cursor predated per-province
consumer-goods allocation (demographics, CG chains) and could no longer
describe the queries. These checks hold for any CG formula:
  * consumed CG never exceeds the stock,
  * with ample stock, consumption equals the nation's full need (> 0),
  * having consumer goods never lowers tax income,
  * no provinces -> no income,
  * no retail buildings -> no consumer goods reach anyone (by design since
    the 2026-09-25 per-province distribution change).
"""
import uuid

import pytest

from database import get_db_connection
from tests._db_cleanup import purge_users


def _make_nation(db, consumer_goods, retail=True):
    name = f"ti_{uuid.uuid4().hex[:8]}"
    db.execute(
        "INSERT INTO users (username, email, date, hash, auth_type) "
        "VALUES (%s, %s, '2026-10-06', 'x', 'normal') RETURNING id",
        (name, f"{name}@example.invalid"),
    )
    uid = db.fetchone()[0]
    db.execute("INSERT INTO stats (id, location, gold) VALUES (%s, 'Grassland', 0)", (uid,))
    import variables

    retail_building = next(iter(variables.CONSUMER_GOODS_DISTRIBUTION_PER_BUILDING))
    for i in range(2):
        db.execute(
            "INSERT INTO provinces (userid, provincename, citycount, land, population, "
            "happiness, productivity, pop_children, pop_working, pop_elderly) "
            "VALUES (%s, %s, 5, 10, 1000000, 60, 60, 200000, 600000, 200000) RETURNING id",
            (uid, f"{name}-{i}"),
        )
        pid = db.fetchone()[0]
        if retail:
            db.execute(
                "INSERT INTO user_buildings (user_id, building_id, province_id, quantity) "
                "SELECT %s, building_id, %s, 1000 FROM building_dictionary WHERE name = %s",
                (uid, pid, retail_building),
            )
    db.execute(
        "INSERT INTO user_economy (user_id, resource_id, quantity) "
        "SELECT %s, resource_id, %s FROM resource_dictionary WHERE name = 'consumer_goods'",
        (uid, consumer_goods),
    )
    return uid


@pytest.fixture
def nations():
    with get_db_connection() as conn:
        db = conn.cursor()
        ids = {
            "none": _make_nation(db, 0),
            "one": _make_nation(db, 1),
            "plenty": _make_nation(db, 10**9),
            "no_shops": _make_nation(db, 10**9, retail=False),
        }
        db.execute(
            "INSERT INTO users (username, email, date, hash, auth_type) "
            "VALUES (%s, %s, '2026-10-06', 'x', 'normal') RETURNING id",
            (f"ti_np_{uuid.uuid4().hex[:6]}", f"np{uuid.uuid4().hex[:6]}@example.invalid"),
        )
        ids["no_provinces"] = db.fetchone()[0]
        conn.commit()
    yield ids
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("DELETE FROM provinces WHERE userid = ANY(%s)", (list(ids.values()),))
        db.execute("DELETE FROM user_economy WHERE user_id = ANY(%s)", (list(ids.values()),))
        db.execute("DELETE FROM user_buildings WHERE user_id = ANY(%s)", (list(ids.values()),))
        purge_users(db, list(ids.values()))
        conn.commit()


@pytest.mark.no_server
def test_calc_ti_consumer_goods_bounds_and_effect(nations):
    from app_core.game_ticks.taxes import calc_ti

    income_none, removed_none = calc_ti(nations["none"])
    income_one, removed_one = calc_ti(nations["one"])
    income_plenty, removed_plenty = calc_ti(nations["plenty"])

    assert removed_none == 0
    assert removed_one == 1                    # never more than the stock
    assert removed_plenty > 1                  # full need of 2M people
    assert removed_plenty < 10**9              # ...and not the whole stock
    assert income_none > 0
    assert income_plenty >= income_one >= income_none
    assert income_plenty > income_none          # CG coverage raises tax income

    income_ns, removed_ns = calc_ti(nations["no_shops"])
    assert removed_ns == 0                      # nothing distributes it
    assert income_ns == income_none


@pytest.mark.no_server
def test_calc_ti_without_provinces_pays_nothing(nations):
    from app_core.game_ticks.taxes import calc_ti

    income, removed = calc_ti(nations["no_provinces"])
    assert not income and not removed
