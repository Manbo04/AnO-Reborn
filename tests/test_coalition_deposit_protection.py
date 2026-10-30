"""Safe Personal Deposit opt-in (#suggestions 1558896941574651974).

DB-free: view/service functions run in a bare Flask request context against a
scripted cursor, so these check the reserve rule, not Postgres.
"""
import pytest
from flask import Flask, session

from app_core.coalitions import repositories, routes
from tests._fake_db import FakeCursor, cursor_ctx

pytestmark = pytest.mark.no_server

VAULT = 100


@pytest.fixture
def app(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "test"
    monkeypatch.setattr(routes, "_require_coalition_member", lambda *a, **k: None)
    monkeypatch.setattr(routes, "_invalidate_bank_caches", lambda *a, **k: None)
    monkeypatch.setattr(routes.ledger, "credit_gold", lambda *a, **k: None)
    return app


def _install(monkeypatch, cursor):
    monkeypatch.setattr(routes, "get_request_cursor", cursor_ctx(cursor))


def _debited_vault(cursor):
    return any("UPDATE colBanks" in sql for sql in cursor.sql_log())


def test_protected_balance_blocks_banker_over_withdrawal(app, monkeypatch):
    # Member 2 protects 50 money; banker 1 tries to take 80 of the 100 vault.
    cur = FakeCursor(
        [
            ("FILTER", [(50, 0)]),
            ("SELECT money FROM colBanks", [(VAULT,)]),
            ("UPDATE colBanks", [(VAULT - 80,)]),
        ]
    )
    _install(monkeypatch, cur)
    with app.test_request_context("/x", method="POST"):
        session["user_id"] = 1
        resp = routes.withdraw("money", 80, 1, 7)
    assert resp is not None and resp.headers["Location"].endswith("#bank")
    assert not _debited_vault(cur)


def test_banker_can_take_what_exceeds_the_reserve(app, monkeypatch):
    cur = FakeCursor(
        [
            ("FILTER", [(50, 0)]),
            ("SELECT money FROM colBanks", [(VAULT,)]),
            ("UPDATE colBanks", [(VAULT - 50,)]),
            ("SELECT gold", [(10,)]),
        ]
    )
    _install(monkeypatch, cur)
    with app.test_request_context("/x", method="POST"):
        session["user_id"] = 1
        assert routes.withdraw("money", 50, 1, 7) is None
    assert _debited_vault(cur)


def test_unprotected_members_do_not_reserve_anything(app, monkeypatch):
    # No protected rows -> the reserve query sums to 0 and the banker proceeds.
    cur = FakeCursor(
        [
            ("FILTER", [(0, 0)]),
            ("SELECT money FROM colBanks", [(VAULT,)]),
            ("UPDATE colBanks", [(0,)]),
            ("SELECT gold", [(10,)]),
        ]
    )
    _install(monkeypatch, cur)
    with app.test_request_context("/x", method="POST"):
        session["user_id"] = 1
        assert routes.withdraw("money", VAULT, 1, 7) is None
    assert _debited_vault(cur)


def test_owner_can_still_withdraw_own_protected_balance(app, monkeypatch):
    # Protected member 2 withdraws their own 50 through the personal route.
    cur = FakeCursor(
        [
            ("FROM col_bank_contributions", [(50, 0)]),
            ("UPDATE colBanks", [(VAULT - 50,)]),
        ]
    )
    _install(monkeypatch, cur)
    with app.test_request_context("/x", method="POST", data={"money": "50"}):
        session["user_id"] = 2
        resp = routes.withdraw_personal_from_bank(7)
    assert resp.headers["Location"].endswith("#bank")
    assert _debited_vault(cur)
    assert not any("col_deposit_protection" in s for s in cur.sql_log())


def test_reserve_helper_counts_protected_recipient_after_payout(monkeypatch):
    # Recipient is protected with 50: paying them 30 leaves 20 reserved for
    # them, plus 10 for another protected member.
    cur = FakeCursor([("FILTER", [(10, 50)])])
    assert repositories.protected_reserve_after(cur, 7, "money", 2, 30) == 30


def test_reserve_fails_open_when_table_is_missing():
    class Boom(FakeCursor):
        def execute(self, sql, params=None):
            if "col_deposit_protection" in str(sql):
                raise RuntimeError("relation does not exist")
            super().execute(sql, params)

    assert repositories.protected_reserve_after(Boom(), 7, "money", 2, 30) == 0
    assert repositories.is_deposit_protected(Boom(), 7, 2) is False
    assert repositories.protected_reserves(Boom(), 7) == {}
