"""Coverage for app_core/loans - repository SQL/param sanity plus service-layer
validation branches (cap, min amount, one-active-loan rule, repayment).
Same queued-fake-cursor style as tests/test_treaties_services.py.
"""

import pytest

import variables
from app_core.loans import repositories
from app_core.loans import services

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

def test_get_active_loan_returns_row():
    db = QueuedCursor([(1, 500000, 500000, 0.01, "2026-09-07")])
    row = repositories.get_active_loan(db, 42)
    assert row[0] == 1
    sql, params = db.calls[-1]
    assert "status = 'active'" in sql
    assert params == (42,)


def test_get_total_population_defaults_to_zero():
    db = QueuedCursor([(None,)])
    assert repositories.get_total_population(db, 1) == 0


def test_get_total_population_returns_sum():
    db = QueuedCursor([(2_500_000,)])
    assert repositories.get_total_population(db, 1) == 2_500_000


def test_get_gold_defaults_to_zero_when_no_row():
    db = QueuedCursor([None])
    assert repositories.get_gold(db, 1) == 0.0


def test_insert_loan_returns_new_id():
    db = QueuedCursor([(9,)])
    loan_id = repositories.insert_loan(db, 1, 500000, 0.01)
    assert loan_id == 9
    sql, params = db.calls[-1]
    assert "INSERT INTO user_loans" in sql
    assert params == (1, 500000, 500000, 0.01)


def test_mark_loan_repaid_sets_status_and_zeroes_balance():
    db = QueuedCursor()
    repositories.mark_loan_repaid(db, 5)
    sql, params = db.calls[-1]
    assert "status = 'repaid'" in sql
    assert "balance = 0" in sql
    assert params == (5,)


# ---------------------------------------------------------------------------
# services.compute_loan_cap / get_loan_status
# ---------------------------------------------------------------------------

def test_compute_loan_cap_scales_with_population():
    db = QueuedCursor([(1_000_000,)])
    cap = services.compute_loan_cap(db, 1)
    assert cap == 1_000_000 * variables.LOAN_CAP_PER_POPULATION


def test_get_loan_status_no_active_loan(monkeypatch):
    monkeypatch.setattr(services, "get_active_loan", lambda db, uid: None)
    monkeypatch.setattr(services, "compute_loan_cap", lambda db, uid: 40_000_000)
    status = services.get_loan_status(None, 1)
    assert status["has_active_loan"] is False
    assert status["cap"] == 40_000_000
    assert status["min_amount"] == variables.LOAN_MIN_AMOUNT


def test_get_loan_status_with_active_loan(monkeypatch):
    monkeypatch.setattr(
        services, "get_active_loan",
        lambda db, uid: (7, 1_000_000, 800_000, 0.01, "2026-09-01"),
    )
    monkeypatch.setattr(services, "compute_loan_cap", lambda db, uid: 40_000_000)
    status = services.get_loan_status(None, 1)
    assert status["has_active_loan"] is True
    assert status["loan_id"] == 7
    assert status["principal"] == 1_000_000
    assert status["balance"] == 800_000
    assert status["hourly_interest"] == 8_000


# ---------------------------------------------------------------------------
# services.take_loan
# ---------------------------------------------------------------------------

def test_take_loan_rejects_when_already_active(monkeypatch):
    monkeypatch.setattr(services, "get_active_loan", lambda db, uid: (1, 1, 1, 0.01, "x"))
    ok, err, category = services.take_loan(None, 1, 500000)
    assert ok is False
    assert "already have an active loan" in err


def test_take_loan_rejects_invalid_amount(monkeypatch):
    monkeypatch.setattr(services, "get_active_loan", lambda db, uid: None)
    ok, err, category = services.take_loan(None, 1, "not-a-number")
    assert ok is False
    assert category == "danger"


def test_take_loan_rejects_below_minimum(monkeypatch):
    monkeypatch.setattr(services, "get_active_loan", lambda db, uid: None)
    ok, err, category = services.take_loan(None, 1, 1)
    assert ok is False
    assert "Minimum loan amount" in err


def test_take_loan_rejects_above_cap(monkeypatch):
    monkeypatch.setattr(services, "get_active_loan", lambda db, uid: None)
    monkeypatch.setattr(services, "compute_loan_cap", lambda db, uid: 1_000_000)
    ok, err, category = services.take_loan(None, 1, 2_000_000)
    assert ok is False
    assert "exceeds your borrowing capacity" in err


def test_take_loan_success(monkeypatch):
    monkeypatch.setattr(services, "get_active_loan", lambda db, uid: None)
    monkeypatch.setattr(services, "compute_loan_cap", lambda db, uid: 40_000_000)
    insert_calls = []
    credit_calls = []
    monkeypatch.setattr(
        services, "insert_loan",
        lambda db, uid, amount, rate: insert_calls.append((uid, amount, rate)),
    )
    monkeypatch.setattr(
        services, "credit_gold",
        lambda db, uid, amount: credit_calls.append((uid, amount)),
    )
    ok, err, category = services.take_loan(None, 1, 500_000)
    assert ok is True
    assert insert_calls == [(1, 500_000, variables.LOAN_INTEREST_RATE_HOURLY)]
    assert credit_calls == [(1, 500_000)]


# ---------------------------------------------------------------------------
# services.repay_loan
# ---------------------------------------------------------------------------

def test_repay_loan_rejects_when_no_active_loan(monkeypatch):
    monkeypatch.setattr(services, "get_active_loan", lambda db, uid: None)
    ok, err, category = services.repay_loan(None, 1, 100)
    assert ok is False
    assert "don't have an active loan" in err


def test_repay_loan_rejects_insufficient_gold(monkeypatch):
    monkeypatch.setattr(services, "get_active_loan", lambda db, uid: (1, 1000, 1000, 0.01, "x"))
    monkeypatch.setattr(services, "get_gold", lambda db, uid: 50)
    ok, err, category = services.repay_loan(None, 1, 100)
    assert ok is False
    assert "enough gold" in err


def test_repay_loan_partial_updates_balance(monkeypatch):
    monkeypatch.setattr(services, "get_active_loan", lambda db, uid: (1, 1000, 1000, 0.01, "x"))
    monkeypatch.setattr(services, "get_gold", lambda db, uid: 5000)
    debit_calls = []
    update_calls = []
    monkeypatch.setattr(services, "debit_gold", lambda db, uid, amt: debit_calls.append((uid, amt)))
    monkeypatch.setattr(services, "update_loan_balance", lambda db, loan_id, bal: update_calls.append((loan_id, bal)))
    ok, err, category = services.repay_loan(None, 1, 400)
    assert ok is True
    assert debit_calls == [(1, 400)]
    assert update_calls == [(1, 600)]


def test_repay_loan_full_marks_repaid(monkeypatch):
    monkeypatch.setattr(services, "get_active_loan", lambda db, uid: (1, 1000, 1000, 0.01, "x"))
    monkeypatch.setattr(services, "get_gold", lambda db, uid: 5000)
    repaid_calls = []
    monkeypatch.setattr(services, "debit_gold", lambda db, uid, amt: None)
    monkeypatch.setattr(services, "mark_loan_repaid", lambda db, loan_id: repaid_calls.append(loan_id))
    ok, err, category = services.repay_loan(None, 1, 1000)
    assert ok is True
    assert repaid_calls == [1]


def test_repay_loan_overpayment_caps_at_balance(monkeypatch):
    monkeypatch.setattr(services, "get_active_loan", lambda db, uid: (1, 1000, 1000, 0.01, "x"))
    monkeypatch.setattr(services, "get_gold", lambda db, uid: 5000)
    debit_calls = []
    repaid_calls = []
    monkeypatch.setattr(services, "debit_gold", lambda db, uid, amt: debit_calls.append(amt))
    monkeypatch.setattr(services, "mark_loan_repaid", lambda db, loan_id: repaid_calls.append(loan_id))
    ok, err, category = services.repay_loan(None, 1, 5000)  # tries to overpay
    assert ok is True
    assert debit_calls == [1000]  # capped at the outstanding balance, not 5000
    assert repaid_calls == [1]
