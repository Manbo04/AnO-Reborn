from flask import session

import market
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
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self._cursor

    def __exit__(self, exc_type, exc, tb):
        return False


def test_sell_market_offer_not_enough_resources(monkeypatch):
    # Offer: resource 'steel', total_amount 100, price, buyer id
    fake_cursor = FakeCursor(fetchone_rows=[("steel", 100, 10, 2), (5,)])
    monkeypatch.setattr(
        market.psycopg2, "connect", lambda *a, **kw: FakeConn(fake_cursor)
    )

    with app.test_request_context(method="POST", data={"amount_1": "10"}):
        session["user_id"] = 2  # seller
        resp = market.sell_market_offer.__wrapped__("1")
        assert isinstance(resp, tuple)
        assert resp[1] == 400


def test_transfer_insufficient_resources(monkeypatch):
    # transfer route: resource 'steel', amount 10, user has only 3
    fake_cursor = FakeCursor(fetchone_rows=[(3,)])
    monkeypatch.setattr(
        market.psycopg2, "connect", lambda *a, **kw: FakeConn(fake_cursor)
    )

    with app.test_request_context(
        method="POST", data={"resource": "steel", "amount": "10"}
    ):
        session["user_id"] = 4
        resp = market.transfer.__wrapped__("5")  # transferee id
        assert isinstance(resp, tuple)
        assert resp[1] == 400


def test_delete_offer_not_owner(monkeypatch):
    # delete_offer uses get_db_cursor() to fetch offer owner
    fake_cursor = FakeCursor(fetchone_rows=[(99,)])
    monkeypatch.setattr(market, "get_db_cursor", lambda *a, **kw: FakeCtx(fake_cursor))

    with app.test_request_context(method="POST"):
        session["user_id"] = 1
        resp = market.delete_offer.__wrapped__("1")
        assert isinstance(resp, tuple)
        assert resp[1] == 400
