from flask import session

import market
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


class FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def commit(self):
        pass

    def close(self):
        pass


def test_buy_market_offer_not_enough_money(monkeypatch):
    # Offer: price 10, total_amount 100, seller_id 2
    fake_cursor = FakeCursor(fetch_rows=[["steel", 100, 10, 2], [5]])
    monkeypatch.setattr(
        market.psycopg2, "connect", lambda *a, **kw: FakeConn(fake_cursor)
    )

    with app.test_request_context(method="POST", data={"amount_1": "10"}):
        session["user_id"] = 3
        resp = market.buy_market_offer.__wrapped__("1")
        assert isinstance(resp, tuple)
        assert resp[1] == 400
