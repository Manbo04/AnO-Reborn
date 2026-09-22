"""Coverage for app_core/bonds - repository SQL/param sanity plus
service-layer validation branches (issuance cap, term bounds, self-lending
guard, default cooldown). Same queued-fake-cursor style as
tests/test_loans_services.py.
"""

import pytest

import variables
from app_core.bonds import repositories
from app_core.bonds import services

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

def test_get_outstanding_bond_principal_defaults_to_zero():
    db = QueuedCursor([None])
    assert repositories.get_outstanding_bond_principal(db, 1) == 0.0


def test_get_outstanding_bond_principal_sums_listed_and_active():
    db = QueuedCursor([(1_500_000,)])
    assert repositories.get_outstanding_bond_principal(db, 1) == 1_500_000.0
    sql, params = db.calls[-1]
    assert "'listed', 'active'" in sql
    assert params == (1,)


def test_insert_bond_returns_new_id():
    db = QueuedCursor([(11,)])
    bond_id = repositories.insert_bond(db, 1, 500000, 0.01, 10, False)
    assert bond_id == 11
    sql, params = db.calls[-1]
    assert "INSERT INTO bonds" in sql
    assert params == (1, 500000, 0.01, 10, False)


def test_fund_bond_guards_on_listed_status():
    db = QueuedCursor([None])
    result = repositories.fund_bond(db, 5, 2, 10)
    assert result is None
    sql, params = db.calls[-1]
    assert "status='listed'" in sql or "status = 'listed'" in sql
    assert params == (2, 10, 5)


def test_cancel_bond_scopes_to_issuer_and_listed_status():
    db = QueuedCursor([(5,)])
    result = repositories.cancel_bond(db, 5, 1)
    assert result == (5,)
    sql, params = db.calls[-1]
    assert "status = 'cancelled'" in sql
    assert params == (5, 1)


# ---------------------------------------------------------------------------
# services.compute_bond_cap / default_cooldown_remaining
# ---------------------------------------------------------------------------

def test_compute_bond_cap_scales_with_population():
    db = QueuedCursor([(2_000_000,)])
    cap = services.compute_bond_cap(db, 1)
    assert cap == 2_000_000 * variables.BOND_CAP_PER_POPULATION


def test_default_cooldown_none_when_never_defaulted(monkeypatch):
    monkeypatch.setattr(services, "get_last_default_resolved_at", lambda db, uid: None)
    assert services.default_cooldown_remaining(None, 1) == 0.0


def test_default_cooldown_expired_after_window(monkeypatch):
    from datetime import datetime, timedelta, timezone

    long_ago = datetime.now(timezone.utc) - timedelta(days=variables.BOND_DEFAULT_COOLDOWN_DAYS + 1)
    monkeypatch.setattr(services, "get_last_default_resolved_at", lambda db, uid: long_ago)
    assert services.default_cooldown_remaining(None, 1) == 0.0


def test_default_cooldown_positive_within_window(monkeypatch):
    from datetime import datetime, timedelta, timezone

    recently = datetime.now(timezone.utc) - timedelta(days=1)
    monkeypatch.setattr(services, "get_last_default_resolved_at", lambda db, uid: recently)
    remaining = services.default_cooldown_remaining(None, 1)
    assert remaining > 0


# ---------------------------------------------------------------------------
# services.create_bond
# ---------------------------------------------------------------------------

def test_create_bond_blocked_during_default_cooldown(monkeypatch):
    db = QueuedCursor()
    monkeypatch.setattr(services, "default_cooldown_remaining", lambda db, uid: 5.0)
    ok, err, category = services.create_bond(db, 1, 500000, 1.0, 10, False)
    assert ok is False
    assert "defaulted" in err


def test_create_bond_rejects_below_minimum_principal(monkeypatch):
    db = QueuedCursor()
    monkeypatch.setattr(services, "default_cooldown_remaining", lambda db, uid: 0.0)
    ok, err, category = services.create_bond(
        db, 1, variables.BOND_MIN_PRINCIPAL - 1, 0.01, 10, False
    )
    assert ok is False
    assert category == "danger"


def test_create_bond_rejects_rate_outside_bounds(monkeypatch):
    db = QueuedCursor()
    monkeypatch.setattr(services, "default_cooldown_remaining", lambda db, uid: 0.0)
    ok, err, category = services.create_bond(
        db, 1, variables.BOND_MIN_PRINCIPAL, variables.BOND_MAX_INTEREST_RATE + 0.01, 10, False
    )
    assert ok is False
    assert "interest rate" in err


def test_create_bond_rejects_term_outside_bounds(monkeypatch):
    db = QueuedCursor()
    monkeypatch.setattr(services, "default_cooldown_remaining", lambda db, uid: 0.0)
    ok, err, category = services.create_bond(
        db, 1, variables.BOND_MIN_PRINCIPAL, 0.01, variables.BOND_MAX_TERM_DAYS + 1, False
    )
    assert ok is False
    assert "Term" in err


def test_create_bond_rejects_over_issuance_cap(monkeypatch):
    db = QueuedCursor()
    monkeypatch.setattr(services, "default_cooldown_remaining", lambda db, uid: 0.0)
    monkeypatch.setattr(services, "compute_bond_cap", lambda db, uid: 1_000_000)
    monkeypatch.setattr(services, "get_outstanding_bond_principal", lambda db, uid: 900_000)
    ok, err, category = services.create_bond(db, 1, 500_000, 0.01, 10, False)
    assert ok is False
    assert "capacity" in err


def test_create_bond_succeeds_within_cap(monkeypatch):
    db = QueuedCursor()
    monkeypatch.setattr(services, "default_cooldown_remaining", lambda db, uid: 0.0)
    monkeypatch.setattr(services, "compute_bond_cap", lambda db, uid: 10_000_000)
    monkeypatch.setattr(services, "get_outstanding_bond_principal", lambda db, uid: 0)
    inserted = {}
    monkeypatch.setattr(
        services, "insert_bond",
        lambda db, issuer_id, principal, rate, term, escrow: inserted.update(
            issuer_id=issuer_id, principal=principal, rate=rate, term=term, escrow=escrow
        ) or 1,
    )
    ok, err, category = services.create_bond(db, 1, 500_000, 0.01, 10, True)
    assert ok is True
    assert err is None
    assert inserted == {"issuer_id": 1, "principal": 500_000, "rate": 0.01, "term": 10, "escrow": True}


# ---------------------------------------------------------------------------
# services.fund_bond
# ---------------------------------------------------------------------------

def test_fund_bond_rejects_self_lending(monkeypatch):
    db = QueuedCursor()
    bond_row = [None] * 15
    bond_row[services._ID] = 5
    bond_row[services._ISSUER] = 1
    bond_row[services._STATUS] = "listed"
    bond_row[services._PRINCIPAL] = 500000
    bond_row[services._TERM] = 10
    monkeypatch.setattr(services, "get_bond", lambda db, bond_id: tuple(bond_row))
    ok, err, category = services.fund_bond(db, 5, 1)
    assert ok is False
    assert "own bond" in err


def test_fund_bond_rejects_not_listed(monkeypatch):
    db = QueuedCursor()
    bond_row = [None] * 15
    bond_row[services._STATUS] = "active"
    monkeypatch.setattr(services, "get_bond", lambda db, bond_id: tuple(bond_row))
    ok, err, category = services.fund_bond(db, 5, 2)
    assert ok is False
    assert "no longer available" in err


def test_fund_bond_rejects_when_another_lender_wins_race(monkeypatch):
    db = QueuedCursor()
    bond_row = [None] * 15
    bond_row[services._ID] = 5
    bond_row[services._ISSUER] = 1
    bond_row[services._STATUS] = "listed"
    bond_row[services._PRINCIPAL] = 500000
    bond_row[services._TERM] = 10
    monkeypatch.setattr(services, "get_bond", lambda db, bond_id: tuple(bond_row))
    monkeypatch.setattr(services, "lock_users", lambda db, ids: None)
    monkeypatch.setattr(services, "repo_fund_bond", lambda db, bond_id, lender_id, term_days: None)
    ok, err, category = services.fund_bond(db, 5, 2)
    assert ok is False
    assert "funded by someone else" in err
