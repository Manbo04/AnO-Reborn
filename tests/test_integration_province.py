"""Buying a building through the real /buy route and schema.

Replaces a fake-cursor test of the legacy proInfra/resources tables (gone
since the normalized user_buildings/user_economy migration)."""
import pytest

import variables
from database import get_db_connection, query_cache
from tests._session import mark_validated

pytestmark = pytest.mark.no_server

UID, PROVINCE = 16, 101  # db/test_seed.sql


def _snapshot(db):
    db.execute("SELECT gold FROM stats WHERE id = %s", (UID,))
    gold = int(db.fetchone()[0])
    db.execute(
        "SELECT COALESCE(SUM(ue.quantity), 0) FROM user_economy ue "
        "JOIN resource_dictionary rd ON rd.resource_id = ue.resource_id "
        "WHERE ue.user_id = %s AND rd.name = 'lumber'",
        (UID,),
    )
    lumber = int(db.fetchone()[0])
    db.execute(
        "SELECT COALESCE(SUM(ub.quantity), 0) FROM user_buildings ub "
        "JOIN building_dictionary bd ON bd.building_id = ub.building_id "
        "WHERE ub.user_id = %s AND ub.province_id = %s AND bd.name = 'farms'",
        (UID, PROVINCE),
    )
    farms = int(db.fetchone()[0])
    return gold, lumber, farms


@pytest.fixture
def funded():
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("UPDATE stats SET gold = 50000000 WHERE id = %s", (UID,))
        db.execute(
            "INSERT INTO user_economy (user_id, resource_id, quantity) "
            "SELECT %s, resource_id, 1000000 FROM resource_dictionary WHERE name = 'lumber' "
            "ON CONFLICT (user_id, resource_id) DO UPDATE SET quantity = 1000000",
            (UID,),
        )
        db.execute(
            "DELETE FROM user_buildings WHERE user_id = %s AND province_id = %s", (UID, PROVINCE)
        )
        conn.commit()
    yield
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            "DELETE FROM user_buildings WHERE user_id = %s AND province_id = %s", (UID, PROVINCE)
        )
        conn.commit()


def test_province_buy_integration(funded):
    from app import app

    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with get_db_connection() as conn:
        gold0, lumber0, farms0 = _snapshot(conn.cursor())
    query_cache.set(f"resources_{UID}", {"lumber": lumber0}, ttl_seconds=60)

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user_id"] = UID
            mark_validated(sess)
        resp = client.post(f"/buy/farms/{PROVINCE}", data={"farms": "1"})
    assert resp.status_code in (200, 302, 303), resp.status_code

    with get_db_connection() as conn:
        gold1, lumber1, farms1 = _snapshot(conn.cursor())
    prices = variables.PROVINCE_UNIT_PRICES
    assert farms1 == farms0 + 1
    assert gold0 - gold1 == prices["farms_price"]
    assert lumber0 - lumber1 == prices["farms_resource"]["lumber"]
    # the cached resource bar must not show pre-purchase lumber
    assert query_cache.get(f"resources_{UID}") != {"lumber": lumber0}
