"""Coverage for app_core/treaties - there was no test file for the old flat
treaties.py at all, so this covers both the repository queries (right SQL /
right params) and the service-layer validation branches.

Uses a queued-result fake cursor, same style as
tests/test_trade_agreement_services.py: execute() just records calls,
fetchone()/fetchall() pop the next preset result in call order.
"""

import pytest

from app_core.treaties import repositories
from app_core.treaties import services

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


class RaisingCursor:
    """Raises on the second execute() call, to exercise list_treaties'
    try/except/rollback path."""

    def __init__(self, first_result):
        self._first_result = first_result
        self.calls = 0

    def execute(self, sql, params=None):
        self.calls += 1
        if self.calls == 2:
            raise RuntimeError("simulated query failure")

    def fetchall(self):
        return self._first_result


# ---------------------------------------------------------------------------
# repositories - SQL/param sanity
# ---------------------------------------------------------------------------

def test_find_conflicting_treaty_checks_both_directions():
    db = QueuedCursor([(9,)])
    row = repositories.find_conflicting_treaty(db, "non_aggression", 1, 2)
    assert row == (9,)
    sql, params = db.calls[-1]
    assert params == ("non_aggression", 1, 2, 2, 1)


def test_activate_treaty_requires_recipient_and_pending():
    db = QueuedCursor()
    repositories.activate_treaty(db, 5, 42)
    sql, params = db.calls[-1]
    assert "status = 'active'" in sql
    assert "recipient_id = %s" in sql
    assert "status = 'pending'" in sql
    assert params == (5, 42)


def test_set_treaty_cancelled_allows_either_party():
    db = QueuedCursor()
    repositories.set_treaty_cancelled(db, 5, 42)
    sql, params = db.calls[-1]
    assert "sender_id = %s OR recipient_id = %s" in sql
    assert params == (5, 42, 42)


# ---------------------------------------------------------------------------
# services.offer_treaty
# ---------------------------------------------------------------------------

def test_offer_treaty_rejects_invalid_type():
    ok, err, category = services.offer_treaty(None, 1, "someone", "war_pact")
    assert ok is False
    assert err == "Invalid treaty type."
    assert category == "danger"


def test_offer_treaty_nation_not_found():
    db = QueuedCursor([None])
    ok, err, category = services.offer_treaty(db, 1, "nobody", "non_aggression")
    assert ok is False
    assert err == "Nation not found."
    assert category == "danger"


def test_offer_treaty_rejects_self():
    db = QueuedCursor([(1,)])  # recipient_id resolves to the same user
    ok, err, category = services.offer_treaty(db, 1, "myself", "non_aggression")
    assert ok is False
    assert "yourself" in err
    assert category == "danger"


def test_offer_treaty_rejects_duplicate():
    db = QueuedCursor([
        (2,),   # recipient found
        (99,),  # conflicting treaty row found
    ])
    ok, err, category = services.offer_treaty(db, 1, "rival", "non_aggression")
    assert ok is False
    assert "already pending or active" in err
    assert category == "warning"


def test_offer_treaty_accepts_embassy_type():
    db = QueuedCursor([
        (2,),    # recipient found
        None,    # no conflicting treaty
    ])
    ok, err, category = services.offer_treaty(db, 1, "rival", "embassy")
    assert ok is True
    assert db.calls[-1][1] == (1, 2, "embassy")


def test_offer_treaty_success():
    db = QueuedCursor([
        (2,),    # recipient found
        None,    # no conflicting treaty
    ])
    ok, err, category = services.offer_treaty(db, 1, "rival", "mutual_defense")
    assert ok is True
    assert err is None
    assert category is None
    assert "INSERT INTO nation_treaties" in db.calls[-1][0]
    assert db.calls[-1][1] == (1, 2, "mutual_defense")


# ---------------------------------------------------------------------------
# services.list_treaties
# ---------------------------------------------------------------------------

def test_list_treaties_returns_all_three_lists_in_order():
    db = QueuedCursor([
        [("active-row",)],
        [("incoming-row",)],
        [("outgoing-row",)],
    ])
    active, incoming, outgoing = services.list_treaties(db, 1)
    assert active == [("active-row",)]
    assert incoming == [("incoming-row",)]
    assert outgoing == [("outgoing-row",)]


def test_list_treaties_rolls_back_and_returns_empty_on_error(monkeypatch):
    calls = []
    monkeypatch.setattr("database.rollback_db_cursor", lambda db: calls.append(db))

    db = RaisingCursor([("active-row",)])
    active, incoming, outgoing = services.list_treaties(db, 1)

    assert (active, incoming, outgoing) == ([], [], [])
    assert calls == [db]
