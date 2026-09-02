"""Coverage for trade agreement repository/service logic that had no tests
before the app_core.trade_agreements migration: balance checks, and the
accept/reject/cancel/resume/execute state-machine branches.

Uses a queued-result fake cursor (same spirit as tests/test_trade_agreement_create.py's
FakeCursor) rather than a full SQL-simulating engine: each function under test
executes queries in a known, fixed order, so we just queue up what each
fetchone()/fetchall() should return next.
"""

import pytest

from app_core.trade_agreements.repositories import check_resource_balance
from app_core.trade_agreements import services

pytestmark = pytest.mark.no_server


class QueuedCursor:
    """Fake DB cursor: execute() just records calls, fetchone/fetchall pop
    the next preset result in call order."""

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
# check_resource_balance
# ---------------------------------------------------------------------------

def test_check_resource_balance_money_sufficient():
    db = QueuedCursor([(500,)])
    ok, balance = check_resource_balance(db, 1, "money", 100)
    assert ok is True
    assert balance == 500


def test_check_resource_balance_resource_insufficient():
    db = QueuedCursor([(3,)])
    ok, balance = check_resource_balance(db, 1, "rations", 10)
    assert ok is False
    assert balance == 3


def test_check_resource_balance_no_row_defaults_to_zero():
    db = QueuedCursor([None])
    ok, balance = check_resource_balance(db, 1, "rations", 1)
    assert ok is False
    assert balance == 0


# ---------------------------------------------------------------------------
# create_agreement
# ---------------------------------------------------------------------------

def test_create_agreement_rejects_missing_fields():
    ok, err = services.create_agreement(
        None, 1, None, "", "money", 10, "rations", 5, 24, None, ""
    )
    assert ok is False
    assert "required" in err.lower()


def test_create_agreement_rejects_non_numeric_amount():
    ok, err = services.create_agreement(
        None, 1, "2", "", "money", "not-a-number", "rations", 5, 24, None, ""
    )
    assert ok is False
    assert "numeric" in err.lower()


def test_create_agreement_rejects_invalid_interval():
    ok, err = services.create_agreement(
        None, 1, "2", "", "money", 10, "rations", 5, 999, None, ""
    )
    assert ok is False
    assert "interval" in err.lower()


def test_create_agreement_rejects_negative_amount():
    # Note: amount=0 is falsy and instead trips the earlier "all required
    # fields" check (existing behavior, preserved as-is by this migration).
    ok, err = services.create_agreement(
        None, 1, "2", "", "money", -5, "rations", 5, 24, None, ""
    )
    assert ok is False
    assert "at least 1" in err


def test_create_agreement_partner_not_found():
    db = QueuedCursor([None])  # resolve_trade_partner_id: no matching user
    ok, err = services.create_agreement(
        db, 1, "2", "", "money", 10, "rations", 5, 24, None, ""
    )
    assert ok is False
    assert "not found" in err.lower()


def test_create_agreement_insufficient_proposer_balance():
    db = QueuedCursor([
        (2,),   # resolve_trade_partner_id -> partner id 2
        (5,),   # check_resource_balance -> only has 5 gold
    ])
    ok, err = services.create_agreement(
        db, 1, "2", "", "money", 10, "rations", 5, 24, None, ""
    )
    assert ok is False
    assert "Gold" in err  # TRADE_RESOURCE_LABELS maps money -> "Gold"


def test_create_agreement_success():
    db = QueuedCursor([
        (2,),    # resolve_trade_partner_id -> partner id 2
        (500,),  # check_resource_balance -> enough gold
        (7,),    # insert_agreement RETURNING id
    ])
    ok, err = services.create_agreement(
        db, 1, "2", "", "money", 10, "rations", 5, 24, None, "hi"
    )
    assert ok is True
    assert err is None
    # last execute() call should be the INSERT
    assert "INSERT INTO trade_agreements" in db.calls[-1][0]


# ---------------------------------------------------------------------------
# accept_agreement / reject_agreement / cancel_agreement / resume_agreement
# ---------------------------------------------------------------------------

def test_accept_agreement_not_found():
    db = QueuedCursor([None])
    ok, err = services.accept_agreement(db, 1, 42)
    assert ok is False
    assert err == "Agreement not found"


def test_accept_agreement_wrong_user():
    db = QueuedCursor([(999, "rations", 5, "pending")])
    ok, err = services.accept_agreement(db, 1, 42)
    assert ok is False
    assert "only accept" in err


def test_accept_agreement_not_pending():
    db = QueuedCursor([(42, "rations", 5, "active")])
    ok, err = services.accept_agreement(db, 1, 42)
    assert ok is False
    assert "no longer pending" in err


def test_accept_agreement_insufficient_balance():
    db = QueuedCursor([
        (42, "rations", 5, "pending"),
        (2,),  # check_resource_balance -> not enough
    ])
    ok, err = services.accept_agreement(db, 1, 42)
    assert ok is False
    assert "don't have enough" in err


def test_accept_agreement_success():
    db = QueuedCursor([
        (42, "rations", 5, "pending"),
        (50,),  # check_resource_balance -> enough
    ])
    ok, err = services.accept_agreement(db, 1, 42)
    assert ok is True
    assert err is None
    assert "SET status = 'active'" in db.calls[-1][0]


def test_reject_agreement_wrong_user():
    db = QueuedCursor([(999, "pending")])
    ok, err = services.reject_agreement(db, 1, 42)
    assert ok is False
    assert "only reject" in err


def test_reject_agreement_success():
    db = QueuedCursor([(42, "pending")])
    ok, err = services.reject_agreement(db, 1, 42)
    assert ok is True
    assert db.calls[-1][1] == ("cancelled", 1)


def test_cancel_agreement_not_a_party():
    db = QueuedCursor([(1, 2, "active")])
    ok, err = services.cancel_agreement(db, 1, 999)
    assert ok is False
    assert "not part of" in err


def test_cancel_agreement_wrong_status():
    db = QueuedCursor([(1, 2, "completed")])
    ok, err = services.cancel_agreement(db, 1, 1)
    assert ok is False
    assert "cannot be cancelled" in err


def test_cancel_agreement_success_by_either_party():
    db = QueuedCursor([(1, 2, "paused")])
    ok, err = services.cancel_agreement(db, 1, 2)  # receiver cancels
    assert ok is True


def test_resume_agreement_not_paused():
    db = QueuedCursor([(1, 2, "active", 24, "money", 10, "rations", 5)])
    ok, err = services.resume_agreement(db, 1, 1)
    assert ok is False
    assert "not paused" in err


def test_resume_agreement_insufficient_receiver_balance():
    db = QueuedCursor([
        (1, 2, "paused", 24, "money", 10, "rations", 5),
        (500,),  # proposer balance ok
        (0,),    # receiver balance insufficient
    ])
    ok, err = services.resume_agreement(db, 1, 1)
    assert ok is False
    assert "Receiver doesn't have enough" in err


def test_resume_agreement_success():
    db = QueuedCursor([
        (1, 2, "paused", 24, "money", 10, "rations", 5),
        (500,),
        (50,),
    ])
    ok, err = services.resume_agreement(db, 1, 1)
    assert ok is True
    assert "status = 'active'" in db.calls[-1][0]


# ---------------------------------------------------------------------------
# execute_trade_agreement - pause-on-insufficient-funds branches
# (the full success path, which also crosses into app_core.market.give_resource,
# is covered end-to-end in tests/test_trade_logging.py with a richer fake DB)
# ---------------------------------------------------------------------------

def test_execute_trade_agreement_not_found():
    db = QueuedCursor([None])
    ok, msg = services.execute_trade_agreement(1, cursor=db)
    assert ok is False
    assert "not active" in msg


def test_execute_trade_agreement_pauses_on_proposer_shortfall():
    agreement_row = (1, 10, "money", 100, 20, "rations", 5, 0, None, 24)
    db = QueuedCursor([
        agreement_row,
        (5,),  # proposer only has 5 gold, needs 100
    ])
    ok, msg = services.execute_trade_agreement(1, cursor=db)
    assert ok is False
    assert "Proposer has insufficient" in msg
    assert "SET status = 'paused'" in db.calls[-1][0]


def test_execute_trade_agreement_pauses_on_receiver_shortfall():
    agreement_row = (1, 10, "money", 100, 20, "rations", 5, 0, None, 24)
    db = QueuedCursor([
        agreement_row,
        (500,),  # proposer has enough
        (0,),    # receiver has none
    ])
    ok, msg = services.execute_trade_agreement(1, cursor=db)
    assert ok is False
    assert "Receiver has insufficient" in msg
    assert "SET status = 'paused'" in db.calls[-1][0]
