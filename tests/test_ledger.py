"""app_core/economy/ledger.py: the single gold/resource write path."""

import pytest

from app_core.economy import ledger

UID = 16


def _gold(db):
    db.execute("SELECT gold FROM stats WHERE id = %s", (UID,))
    return int(db.fetchone()[0])


def _res(db, name):
    db.execute(
        "SELECT COALESCE(SUM(ue.quantity), 0) FROM user_economy ue "
        "JOIN resource_dictionary rd ON rd.resource_id = ue.resource_id "
        "WHERE ue.user_id = %s AND rd.name = %s",
        (UID, name),
    )
    return int(db.fetchone()[0])


@pytest.fixture
def db():
    from database import get_db_connection

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE stats SET gold = 1000 WHERE id = %s", (UID,))
        yield cur
        conn.rollback()


def test_spend_gold_exact_and_refuses_overdraft(db):
    assert ledger.spend_gold(db, UID, 400) == 600
    with pytest.raises(ledger.InsufficientFunds):
        ledger.spend_gold(db, UID, 601)
    assert _gold(db) == 600


def test_take_gold_clamps_and_reports(db):
    assert ledger.take_gold(db, UID, 300) == 300
    assert ledger.take_gold(db, UID, 5000) == 700
    assert _gold(db) == 0


def test_credit_gold_and_negative_rejected(db):
    ledger.credit_gold(db, UID, 5)
    assert _gold(db) == 1005
    with pytest.raises(ValueError):
        ledger.credit_gold(db, UID, -5)


def test_resources_spend_take_credit(db):
    start = _res(db, "steel")
    ledger.credit_resources(db, UID, {"steel": 50})
    assert _res(db, "steel") == start + 50
    ledger.spend_resources(db, UID, {"steel": start + 20})
    assert _res(db, "steel") == 30
    with pytest.raises(ledger.InsufficientFunds):
        ledger.spend_resources(db, UID, {"steel": 31})
    ledger.adjust_resources(db, UID, {"steel": -100, "oil": 0})
    assert _res(db, "steel") == 0


def test_take_resource_returns_what_was_actually_taken(db):
    ledger.adjust_resources(db, UID, {"steel": -10**12})
    ledger.credit_resources(db, UID, {"steel": 40})
    assert ledger.take_resource(db, UID, "steel", 100) == 40
    assert _res(db, "steel") == 0
    assert ledger.take_resource(db, UID, "steel", 5) == 0


def test_batch_forms(db):
    db.execute("SELECT resource_id FROM resource_dictionary WHERE name = %s", ("steel",))
    rid = db.fetchone()[0]
    ledger.adjust_resources(db, UID, {"steel": -10**12})
    ledger.credit_resource_batch(db, [(UID, rid, 30)])
    ledger.adjust_resource_batch(db, [(UID, rid, -50)])
    assert _res(db, "steel") == 0
    ledger.adjust_resource_batch(db, [(UID, rid, 7)])
    ledger.take_resource_batch(db, [(2, UID, rid)])
    assert _res(db, "steel") == 5
    ledger.credit_gold_batch(db, [(10, UID)])
    ledger.take_gold_batch(db, [(5000, UID)])
    assert _gold(db) == 0
