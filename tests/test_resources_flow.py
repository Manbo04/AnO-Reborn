"""give_resource(): the primitive that moves gold/resources between nations
and the bank (market, trades, aid, coalition bank, ...). Real schema.

Replaces fake-cursor tests that patched module attributes which no longer
exist (app_core.market.get_db_connection).
"""
import uuid

import pytest

from app_core.market.services import give_resource
from database import get_db_connection
from tests._db_cleanup import purge_users

pytestmark = pytest.mark.no_server


def _qty(db, uid, resource):
    db.execute(
        "SELECT COALESCE(SUM(ue.quantity), 0) FROM user_economy ue "
        "JOIN resource_dictionary rd ON rd.resource_id = ue.resource_id "
        "WHERE ue.user_id = %s AND rd.name = %s",
        (uid, resource),
    )
    return int(db.fetchone()[0])


def _gold(db, uid):
    db.execute("SELECT gold FROM stats WHERE id = %s", (uid,))
    return int(db.fetchone()[0])


@pytest.fixture
def pair():
    ids = []
    with get_db_connection() as conn:
        db = conn.cursor()
        for tag, gold in (("a", 1000), ("b", 0)):
            name = f"gr_{tag}_{uuid.uuid4().hex[:6]}"
            db.execute(
                "INSERT INTO users (username, email, date, hash, auth_type) "
                "VALUES (%s, %s, '2026-10-06', 'x', 'normal') RETURNING id",
                (name, f"{name}@example.invalid"),
            )
            uid = db.fetchone()[0]
            db.execute(
                "INSERT INTO stats (id, location, gold) VALUES (%s, 'Grassland', %s)",
                (uid, gold),
            )
            ids.append(uid)
        db.execute(
            "INSERT INTO user_economy (user_id, resource_id, quantity) "
            "SELECT %s, resource_id, 500 FROM resource_dictionary WHERE name = 'lumber'",
            (ids[0],),
        )
        conn.commit()
    yield ids
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("DELETE FROM user_economy WHERE user_id = ANY(%s)", (ids,))
        purge_users(db, ids)
        conn.commit()


def test_give_resource_money_bank_to_user(pair):
    a, _ = pair
    assert give_resource("bank", a, "money", 250) is True
    with get_db_connection() as conn:
        assert _gold(conn.cursor(), a) == 1250


def test_give_resource_money_user_insufficient(pair):
    a, b = pair
    result = give_resource(a, b, "money", 5000)
    assert result is not True and "enough" in str(result)
    with get_db_connection() as conn:
        db = conn.cursor()
        assert _gold(db, a) == 1000 and _gold(db, b) == 0  # nothing moved


def test_give_resource_non_money_transfer(pair):
    a, b = pair
    assert give_resource(a, b, "lumber", 200) is True
    with get_db_connection() as conn:
        db = conn.cursor()
        assert _qty(db, a, "lumber") == 300
        assert _qty(db, b, "lumber") == 200
    # more than the giver has: refused, nothing moves
    assert give_resource(a, b, "lumber", 301) is not True
    with get_db_connection() as conn:
        db = conn.cursor()
        assert _qty(db, a, "lumber") == 300 and _qty(db, b, "lumber") == 200


def test_give_resource_rejects_negative_amounts(pair):
    a, b = pair
    assert give_resource(a, b, "money", -10) == "Amount cannot be negative"
