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
    loan_id = repositories.insert_loan(db, 1, 500000, 550000)
    assert loan_id == 9
    sql, params = db.calls[-1]
    assert "INSERT INTO user_loans" in sql
    assert params == (1, 500000, 550000, 0)


def test_get_last_repaid_at_returns_none_when_no_history():
    db = QueuedCursor([None])
    assert repositories.get_last_repaid_at(db, 1) is None


def test_get_last_repaid_at_returns_most_recent():
    db = QueuedCursor([("2026-09-01",)])
    assert repositories.get_last_repaid_at(db, 1) == "2026-09-01"


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
    monkeypatch.setattr(services, "cooldown_remaining", lambda db, uid: None)
    status = services.get_loan_status(None, 1)
    assert status["has_active_loan"] is False
    assert status["cap"] == 40_000_000
    assert status["min_amount"] == variables.LOAN_MIN_AMOUNT
    assert status["origination_fee"] == variables.LOAN_ORIGINATION_FEE
    assert status["cooldown_hours_remaining"] == 0


def test_get_loan_status_no_active_loan_reports_cooldown(monkeypatch):
    from datetime import timedelta

    monkeypatch.setattr(services, "get_active_loan", lambda db, uid: None)
    monkeypatch.setattr(services, "compute_loan_cap", lambda db, uid: 40_000_000)
    monkeypatch.setattr(services, "cooldown_remaining", lambda db, uid: timedelta(hours=5))
    status = services.get_loan_status(None, 1)
    assert status["cooldown_hours_remaining"] == 5.0


def test_get_loan_status_with_active_loan(monkeypatch):
    monkeypatch.setattr(
        services, "get_active_loan",
        lambda db, uid: (7, 1_000_000, 1_100_000, 0, "2026-09-01"),
    )
    monkeypatch.setattr(services, "compute_loan_cap", lambda db, uid: 40_000_000)
    status = services.get_loan_status(None, 1)
    assert status["has_active_loan"] is True
    assert status["loan_id"] == 7
    assert status["principal"] == 1_000_000
    assert status["balance"] == 1_100_000
    assert status["fee_charged"] == 100_000


# ---------------------------------------------------------------------------
# services.compute_fee_rate / cooldown_remaining
# ---------------------------------------------------------------------------

def test_compute_fee_rate_base_below_threshold():
    assert services.compute_fee_rate(1_000_000, 40_000_000) == variables.LOAN_ORIGINATION_FEE


def test_compute_fee_rate_high_utilization_above_threshold():
    cap = 40_000_000
    amount = int(cap * variables.LOAN_HIGH_UTILIZATION_THRESHOLD) + 1
    assert services.compute_fee_rate(amount, cap) == variables.LOAN_HIGH_UTILIZATION_FEE


def test_cooldown_remaining_none_when_never_borrowed(monkeypatch):
    monkeypatch.setattr(services, "get_last_repaid_at", lambda db, uid: None)
    assert services.cooldown_remaining(None, 1) is None


def test_cooldown_remaining_none_after_window_passes(monkeypatch):
    from datetime import datetime, timedelta, timezone

    long_ago = datetime.now(timezone.utc) - timedelta(hours=variables.LOAN_COOLDOWN_HOURS + 1)
    monkeypatch.setattr(services, "get_last_repaid_at", lambda db, uid: long_ago)
    assert services.cooldown_remaining(None, 1) is None


def test_cooldown_remaining_positive_within_window(monkeypatch):
    from datetime import datetime, timedelta, timezone

    recently = datetime.now(timezone.utc) - timedelta(hours=1)
    monkeypatch.setattr(services, "get_last_repaid_at", lambda db, uid: recently)
    remaining = services.cooldown_remaining(None, 1)
    assert remaining is not None
    assert remaining.total_seconds() > 0


# ---------------------------------------------------------------------------
# services.take_loan
# ---------------------------------------------------------------------------

def test_take_loan_rejects_when_already_active(monkeypatch):
    monkeypatch.setattr(services, "get_active_loan", lambda db, uid: (1, 1, 1, 0, "x"))
    ok, err, category = services.take_loan(None, 1, 500000)
    assert ok is False
    assert "already have an active loan" in err


def test_take_loan_rejects_during_cooldown(monkeypatch):
    from datetime import timedelta

    monkeypatch.setattr(services, "get_active_loan", lambda db, uid: None)
    monkeypatch.setattr(services, "cooldown_remaining", lambda db, uid: timedelta(hours=3))
    ok, err, category = services.take_loan(None, 1, 500000)
    assert ok is False
    assert "cooldown" in err


def test_take_loan_rejects_invalid_amount(monkeypatch):
    monkeypatch.setattr(services, "get_active_loan", lambda db, uid: None)
    monkeypatch.setattr(services, "cooldown_remaining", lambda db, uid: None)
    ok, err, category = services.take_loan(None, 1, "not-a-number")
    assert ok is False
    assert category == "danger"


def test_take_loan_rejects_below_minimum(monkeypatch):
    monkeypatch.setattr(services, "get_active_loan", lambda db, uid: None)
    monkeypatch.setattr(services, "cooldown_remaining", lambda db, uid: None)
    ok, err, category = services.take_loan(None, 1, 1)
    assert ok is False
    assert "Minimum loan amount" in err


def test_take_loan_rejects_above_cap(monkeypatch):
    monkeypatch.setattr(services, "get_active_loan", lambda db, uid: None)
    monkeypatch.setattr(services, "cooldown_remaining", lambda db, uid: None)
    monkeypatch.setattr(services, "compute_loan_cap", lambda db, uid: 1_000_000)
    ok, err, category = services.take_loan(None, 1, 2_000_000)
    assert ok is False
    assert "exceeds your borrowing capacity" in err


def test_take_loan_success_charges_base_fee(monkeypatch):
    monkeypatch.setattr(services, "get_active_loan", lambda db, uid: None)
    monkeypatch.setattr(services, "cooldown_remaining", lambda db, uid: None)
    monkeypatch.setattr(services, "compute_loan_cap", lambda db, uid: 40_000_000)
    insert_calls = []
    credit_calls = []
    monkeypatch.setattr(
        services, "insert_loan",
        lambda db, uid, principal, balance: insert_calls.append((uid, principal, balance)),
    )
    monkeypatch.setattr(
        services, "credit_gold",
        lambda db, uid, amount: credit_calls.append((uid, amount)),
    )
    ok, err, category = services.take_loan(None, 1, 500_000)
    assert ok is True
    # 500_000 is well under 70% of the 40M cap -> base 10% fee
    assert insert_calls == [(1, 500_000, 550_000)]
    assert credit_calls == [(1, 500_000)]


def test_take_loan_success_charges_high_utilization_fee(monkeypatch):
    cap = 1_000_000
    amount = 800_000  # > 70% of cap
    monkeypatch.setattr(services, "get_active_loan", lambda db, uid: None)
    monkeypatch.setattr(services, "cooldown_remaining", lambda db, uid: None)
    monkeypatch.setattr(services, "compute_loan_cap", lambda db, uid: cap)
    insert_calls = []
    monkeypatch.setattr(
        services, "insert_loan",
        lambda db, uid, principal, balance: insert_calls.append((uid, principal, balance)),
    )
    monkeypatch.setattr(services, "credit_gold", lambda db, uid, amount: None)
    ok, err, category = services.take_loan(None, 1, amount)
    assert ok is True
    assert insert_calls == [(1, amount, int(round(amount * (1 + variables.LOAN_HIGH_UTILIZATION_FEE))))]


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
