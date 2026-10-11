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
