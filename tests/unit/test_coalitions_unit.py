from flask import session

import coalitions
from app import app


class FakeCursor:
    def __init__(self, fetchone_rows=None, fetchall_rows=None):
        self._fetchone = fetchone_rows or []
        self._fetchall = fetchall_rows or []
        self.executed = []

    def execute(self, query, params=None):
        self.executed.append((query, params))

    def fetchone(self):
        if not self._fetchone:
            return None
        return self._fetchone.pop(0)

    def fetchall(self):
        return self._fetchall


class FakeCtx:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self._cursor

    def __exit__(self, exc_type, exc, tb):
        return False


def test_get_user_role_returns_value(monkeypatch):
    fake_cursor = FakeCursor(fetchone_rows=[("leader",)])
    monkeypatch.setattr(coalitions, "get_db_cursor", lambda: FakeCtx(fake_cursor))

    assert coalitions.get_user_role(1) == "leader"


def test_establish_coalition_already_in_coalition(monkeypatch):
    fake_cursor = FakeCursor(fetchone_rows=[(1,)])
    monkeypatch.setattr(coalitions, "get_db_cursor", lambda: FakeCtx(fake_cursor))

    with app.test_request_context(method="POST", data={"type": "Open", "name": "X"}):
        session["user_id"] = 1
        resp = coalitions.establish_coalition.__wrapped__()
        assert isinstance(resp, tuple)
        assert resp[1] == 403


def test_establish_coalition_invalid_type(monkeypatch):
    # Simulate not in coalition (first fetchone returns None,
    # which triggers the except branch in production code)
    fake_cursor = FakeCursor(fetchone_rows=[None, None])
    monkeypatch.setattr(coalitions, "get_db_cursor", lambda: FakeCtx(fake_cursor))

    with app.test_request_context(
        method="POST", data={"type": "BadType", "name": "N", "description": "d"}
    ):
        session["user_id"] = 2
        resp = coalitions.establish_coalition.__wrapped__()
        assert isinstance(resp, tuple)
        assert resp[1] == 400


def test_establish_coalition_success_inserts(monkeypatch):
    fake_cursor = FakeCursor(fetchone_rows=[None, None, (123,)])
    monkeypatch.setattr(coalitions, "get_db_cursor", lambda: FakeCtx(fake_cursor))

    with app.test_request_context(
        method="POST", data={"type": "Open", "name": "TestCol", "description": "desc"}
    ):
        session["user_id"] = 3
        resp = coalitions.establish_coalition.__wrapped__()
        assert resp.status_code in (301, 302)
        # Location header should point to /coalition/123
        assert "/coalition/123" in resp.headers.get("Location", "")
