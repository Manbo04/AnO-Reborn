"""Coalition form posts return the player to the tab they were on
(#suggestions 1561375947590991984: "stop sending me back to the main page").

Runs without a database: the view functions are called directly inside a bare
Flask request context with a scripted cursor.
"""
import pytest
from flask import Flask

from app_core.coalitions import routes
from tests._fake_db import FakeCursor, cursor_ctx

pytestmark = pytest.mark.no_server


@pytest.fixture
def ctx(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "test"
    monkeypatch.setattr(routes, "_require_coalition_member", lambda *a, **k: None)
    monkeypatch.setattr(routes, "_invalidate_bank_caches", lambda *a, **k: None)
    monkeypatch.setattr(
        routes,
        "get_coalition_settings",
        lambda *a, **k: {"bank_require_requests": False, "bank_self_approve": True},
    )
    monkeypatch.setattr(routes, "withdraw", lambda *a, **k: None)

    def _install(cursor):
        monkeypatch.setattr(routes, "get_request_cursor", cursor_ctx(cursor))

    return app, _install


def _location(resp):
    return resp.headers["Location"]


def test_bank_withdraw_returns_to_bank_tab(ctx):
    app, install = ctx
    install(FakeCursor())
    with app.test_request_context(
        "/withdraw_from_bank/7", method="POST", data={"money": "5"}
    ):
        from flask import session

        session["user_id"] = 1
        resp = routes.withdraw_from_bank(7)
    assert _location(resp).endswith("/coalition/7#bank")


def test_bank_request_accept_returns_to_bank_tab(ctx):
    app, install = ctx
    install(
        FakeCursor(
            [
                ("FROM colBanksRequests", [(7, "money", 5, 2)]),
                ("SELECT role FROM", [("member",)]),
            ]
        )
    )
    with app.test_request_context("/accept_bank_request/3", method="POST"):
        from flask import session

        session["user_id"] = 1
        resp = routes.accept_bank_request(3)
    assert _location(resp).endswith("/coalition/7#bank")


def test_join_request_accept_returns_to_government_tab(ctx, monkeypatch):
    app, install = ctx
    install(FakeCursor([("FROM requests", [(7,)]), ("COUNT(*)", [(3,)])]))
    monkeypatch.setattr(routes, "_members_tbl", lambda: "coalitions")
    with app.test_request_context("/add/9", method="POST"):
        from flask import session

        session["user_id"] = 1
        resp = routes.adding("9")
    assert _location(resp).endswith("/coalition/7#government")
