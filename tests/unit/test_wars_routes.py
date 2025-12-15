from flask import session

import wars.routes as routes
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


class FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def commit(self):
        pass

    def close(self):
        pass


class FakeCtx:
    def __init__(self, conn_or_cursor, is_conn=False):
        self._v = conn_or_cursor
        self._is_conn = is_conn

    def __enter__(self):
        return self._v

    def __exit__(self, exc_type, exc, tb):
        return False


def test_peace_offers_post_invalid_offer_id():
    with app.test_request_context(method="POST", data={"peace_offer": "nah"}):
        session["user_id"] = 1
        resp = routes.peace_offers.__wrapped__()
        assert isinstance(resp, tuple)
        assert resp[1] == 400


def test_peace_offers_post_no_result(monkeypatch):
    # Simulate DB returning no matching war row
    fake_cursor = FakeCursor()
    fake_conn = FakeConn(fake_cursor)
    monkeypatch.setattr(
        routes, "get_db_connection", lambda *a, **kw: FakeCtx(fake_conn, True)
    )

    with app.test_request_context(
        method="POST", data={"peace_offer": "1", "decision": "1"}
    ):
        session["user_id"] = 1
        resp = routes.peace_offers.__wrapped__()
        assert isinstance(resp, tuple)
        assert resp[1] == 400


def test_send_peace_offer_invalid_amount():
    with app.test_request_context(method="POST", data={"gold": "notanint"}):
        session["user_id"] = 1
        resp = routes.send_peace_offer.__wrapped__(1, 2)
        assert isinstance(resp, tuple)
        assert resp[1] == 400


def test_send_peace_offer_success(monkeypatch):
    # Simulate not having a peace_offer_id and that CURRVAL returns 77
    fake_cursor = FakeCursor(fetchone_rows=[(None,), (77,)])
    monkeypatch.setattr(routes, "get_db_cursor", lambda *a, **kw: FakeCtx(fake_cursor))

    with app.test_request_context(method="POST", data={"money": "10"}):
        session["user_id"] = 5
        resp = routes.send_peace_offer.__wrapped__(1, 2)
        # Success should redirect
        assert resp.status_code in (301, 302)
