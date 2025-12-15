import market


class FakeCursor:
    def __init__(self, fetch_rows=None):
        self._fetch_rows = fetch_rows or []
        self.executed = []

    def execute(self, query, params=None):
        self.executed.append((query, params))

    def fetchone(self):
        if not self._fetch_rows:
            return [None]
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


def test_give_resource_invalid_resource(monkeypatch):
    # No DB call should be made for invalid resource
    called = {}

    def fake_connect(*a, **kw):
        called["connected"] = True
        return FakeConn(FakeCursor())

    # Monkeypatch the module's psycopg2.connect to our fake
    monkeypatch.setattr(market.psycopg2, "connect", fake_connect)

    res = market.give_resource(1, 2, "not_a_resource", 10)
    assert res == "No such resource"


def test_give_money_insufficient(monkeypatch):
    # Simulate giver not having enough gold
    fake_cursor = FakeCursor(fetch_rows=[[40]])
    monkeypatch.setattr(
        market.psycopg2, "connect", lambda *a, **kw: FakeConn(fake_cursor)
    )

    res = market.give_resource(1, 2, "money", 100)
    assert res == "Giver doesn't have enough resources to transfer such amount."


def test_give_money_success_updates(monkeypatch):
    # Simulate giver with enough gold; expect updates executed for both
    fake_cursor = FakeCursor(fetch_rows=[[100]])
    conn = FakeConn(fake_cursor)
    monkeypatch.setattr(market.psycopg2, "connect", lambda *a, **kw: conn)

    res = market.give_resource(1, 2, "money", 25)
    assert res is True
    # Expect SELECT then UPDATE for giver then UPDATE for taker
    queries = [q for q, _ in fake_cursor.executed]
    assert any("SELECT gold FROM stats WHERE id=%s" in q for q in queries)
    assert any("UPDATE stats SET gold=gold-%s WHERE id=%s" in q for q in queries)
    assert any("UPDATE stats SET gold=gold+%s WHERE id=%s" in q for q in queries)
