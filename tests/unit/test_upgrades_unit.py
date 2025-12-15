from flask import session

import upgrades
from app import app


class FakeCursor:
    def __init__(self, fetch_rows=None):
        self._fetch_rows = fetch_rows or []
        self.executed = []

    def execute(self, query, params=None):
        self.executed.append((query, params))

    def fetchone(self):
        if not self._fetch_rows:
            return None
        return self._fetch_rows.pop(0)

    def fetchall(self):
        return []


class FakeCtx:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self._cursor

    def __exit__(self, exc_type, exc, tb):
        return False


def test_get_upgrades_no_row(monkeypatch):
    fake_cursor = FakeCursor(fetch_rows=[None])
    monkeypatch.setattr(upgrades, "get_db_cursor", lambda: FakeCtx(fake_cursor))

    assert upgrades.get_upgrades(1) == {}


def test_buy_upgrade_insufficient_gold(monkeypatch):
    fake_cursor = FakeCursor(fetch_rows=[[0]])
    monkeypatch.setattr(upgrades, "get_db_cursor", lambda: FakeCtx(fake_cursor))

    with app.test_request_context():
        session["user_id"] = 1
        resp = upgrades.upgrade_sell_buy.__wrapped__("buy", "strongerexplosives")
        # helpers.error returns (rendered_template, status_code)
        assert isinstance(resp, tuple)
        assert resp[1] == 400


def test_buy_upgrade_success(monkeypatch):
    # Simulate enough gold to buy and verify UPDATE executed
    fake_cursor = FakeCursor(fetch_rows=[[1000000000]])
    ctx = FakeCtx(fake_cursor)
    monkeypatch.setattr(upgrades, "get_db_cursor", lambda: ctx)

    with app.test_request_context():
        session["user_id"] = 1
        resp = upgrades.upgrade_sell_buy.__wrapped__("buy", "strongerexplosives")
        # Successful purchase should redirect
        # flask redirect returns a Response object (werkzeug.wrappers.Response)
        assert resp.status_code in (302, 301)
        # Ensure upgrades update query was executed
        queries = [q for q, _ in fake_cursor.executed]
        assert any("UPDATE upgrades SET strongerexplosives=1" in q for q in queries)
