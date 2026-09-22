"""Coverage for app_core/currency (national currency / central bank):
repository SQL/param sanity plus service-layer mint/redeem validation,
value-neutrality, and concurrency-lock presence. Same queued-fake-cursor
style as tests/test_loans_services.py.
"""

import pytest

import variables
from app_core.currency import repositories
from app_core.currency import services

pytestmark = pytest.mark.no_server


class QueuedCursor:
    def __init__(self, results=()):
        self._results = list(results)
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def fetchone(self):
        return self._results.pop(0) if self._results else None

    def fetchall(self):
        return self._results.pop(0) if self._results else []


# ---------------------------------------------------------------------------
# repositories - SQL/param sanity
# ---------------------------------------------------------------------------

def test_get_gold_and_currency_defaults_to_zero_when_no_row():
    db = QueuedCursor([None])
    assert repositories.get_gold_and_currency(db, 1) == (0.0, 0.0)


def test_get_gold_and_currency_returns_values():
    db = QueuedCursor([(1000, 40)])
    assert repositories.get_gold_and_currency(db, 1) == (1000.0, 40.0)


def test_debit_gold_floors_at_zero_in_sql():
    db = QueuedCursor()
    repositories.debit_gold(db, 1, 50)
    sql, params = db.calls[-1]
    assert "GREATEST(0" in sql
    assert params == (50, 1)


def test_credit_currency_sql():
    db = QueuedCursor()
    repositories.credit_currency(db, 1, 10)
    sql, params = db.calls[-1]
    assert "national_currency_balance = national_currency_balance + %s" in sql
    assert params == (10, 1)


def test_debit_currency_floors_at_zero_in_sql():
    db = QueuedCursor()
    repositories.debit_currency(db, 1, 10)
    sql, params = db.calls[-1]
    assert "GREATEST(0" in sql
    assert params == (10, 1)


def test_log_conversion_records_direction_and_rate():
    db = QueuedCursor()
    repositories.log_conversion(db, 1, "mint", 50, 10, 5)
    sql, params = db.calls[-1]
    assert "INSERT INTO national_currency_conversions" in sql
    assert params == (1, "mint", 50, 10, 5)


# ---------------------------------------------------------------------------
# services.get_currency_status
# ---------------------------------------------------------------------------

def test_get_currency_status_reports_fixed_rate(monkeypatch):
    monkeypatch.setattr(services, "get_gold_and_currency", lambda db, uid: (1000.0, 20.0))
    status = services.get_currency_status(None, 1)
    assert status == {
        "gold": 1000.0,
        "currency_balance": 20.0,
        "rate": variables.CURRENCY_GOLD_PER_UNIT,
    }


# ---------------------------------------------------------------------------
# services.mint_currency
# ---------------------------------------------------------------------------

def test_mint_currency_takes_advisory_lock_first():
    db = QueuedCursor([(0, 0)])  # get_gold_and_currency read after the lock
    services.mint_currency(db, 1, 10)
    assert "pg_advisory_xact_lock" in db.calls[0][0]
    assert db.calls[0][1] == (1,)


def test_mint_currency_rejects_invalid_amount(monkeypatch):
    db = QueuedCursor()
    ok, err, category = services.mint_currency(db, 1, "not-a-number")
    assert ok is False
    assert category == "danger"


def test_mint_currency_rejects_zero_or_negative(monkeypatch):
    db = QueuedCursor()
    ok, err, category = services.mint_currency(db, 1, -5)
    assert ok is False


def test_mint_currency_rejects_insufficient_gold(monkeypatch):
    db = QueuedCursor()
    monkeypatch.setattr(services, "get_gold_and_currency", lambda db, uid: (10.0, 0.0))
    # 10 units * 5 gold/unit = 50 gold needed, only have 10
    ok, err, category = services.mint_currency(db, 1, 10)
    assert ok is False
    assert "enough gold" in err


def test_mint_currency_success_debits_gold_credits_currency(monkeypatch):
    monkeypatch.setattr(services, "get_gold_and_currency", lambda db, uid: (1000.0, 0.0))
    debit_calls = []
    credit_calls = []
    log_calls = []
    monkeypatch.setattr(services, "debit_gold", lambda db, uid, amt: debit_calls.append(amt))
    monkeypatch.setattr(services, "credit_currency", lambda db, uid, amt: credit_calls.append(amt))
    monkeypatch.setattr(services, "log_conversion", lambda db, uid, direction, g, c, r: log_calls.append((direction, g, c, r)))

    db = QueuedCursor()
    ok, err, category = services.mint_currency(db, 1, 10)
    assert ok is True
    assert debit_calls == [10 * variables.CURRENCY_GOLD_PER_UNIT]
    assert credit_calls == [10]
    assert log_calls == [("mint", 10 * variables.CURRENCY_GOLD_PER_UNIT, 10, variables.CURRENCY_GOLD_PER_UNIT)]


# ---------------------------------------------------------------------------
# services.redeem_currency
# ---------------------------------------------------------------------------

def test_redeem_currency_rejects_insufficient_balance(monkeypatch):
    monkeypatch.setattr(services, "get_gold_and_currency", lambda db, uid: (0.0, 2.0))
    db = QueuedCursor()
    ok, err, category = services.redeem_currency(db, 1, 10)
    assert ok is False
    assert "enough" in err.lower() or "much" in err.lower()


def test_redeem_currency_success_debits_currency_credits_gold(monkeypatch):
    monkeypatch.setattr(services, "get_gold_and_currency", lambda db, uid: (0.0, 20.0))
    debit_calls = []
    credit_calls = []
    monkeypatch.setattr(services, "debit_currency", lambda db, uid, amt: debit_calls.append(amt))
    monkeypatch.setattr(services, "credit_gold", lambda db, uid, amt: credit_calls.append(amt))
    monkeypatch.setattr(services, "log_conversion", lambda *a, **k: None)

    db = QueuedCursor()
    ok, err, category = services.redeem_currency(db, 1, 10)
    assert ok is True
    assert debit_calls == [10]
    assert credit_calls == [10 * variables.CURRENCY_GOLD_PER_UNIT]


def test_mint_then_redeem_round_trip_is_value_neutral(monkeypatch):
    """The whole point of a fixed, never-changing rate: minting and then
    redeeming the same units back must leave gold unchanged -- no arbitrage
    window, no gold created from nothing."""
    state = {"gold": 1000.0, "currency": 0.0}

    def fake_get(db, uid):
        return state["gold"], state["currency"]

    def fake_debit_gold(db, uid, amt):
        state["gold"] -= amt

    def fake_credit_gold(db, uid, amt):
        state["gold"] += amt

    def fake_debit_currency(db, uid, amt):
        state["currency"] -= amt

    def fake_credit_currency(db, uid, amt):
        state["currency"] += amt

    monkeypatch.setattr(services, "get_gold_and_currency", fake_get)
    monkeypatch.setattr(services, "debit_gold", fake_debit_gold)
    monkeypatch.setattr(services, "credit_gold", fake_credit_gold)
    monkeypatch.setattr(services, "debit_currency", fake_debit_currency)
    monkeypatch.setattr(services, "credit_currency", fake_credit_currency)
    monkeypatch.setattr(services, "log_conversion", lambda *a, **k: None)

    db = QueuedCursor()
    starting_gold = state["gold"]

    ok, _, _ = services.mint_currency(db, 1, 20)
    assert ok is True
    assert state["gold"] == starting_gold - 20 * variables.CURRENCY_GOLD_PER_UNIT
    assert state["currency"] == 20

    ok, _, _ = services.redeem_currency(db, 1, 20)
    assert ok is True
    assert state["gold"] == starting_gold
    assert state["currency"] == 0
