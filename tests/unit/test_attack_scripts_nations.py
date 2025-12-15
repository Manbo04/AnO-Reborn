import random

import attack_scripts.Nations as nations


class FakeCursor:
    def __init__(self, fetchone_rows=None):
        self._fetchone = fetchone_rows or []
        self.executed = []

    def execute(self, query, params=None):
        self.executed.append((query, params))
        # Simulate invalid resource by raising when query contains bad name
        if "SELECT bad_resource" in query:
            raise Exception("invalid")

    def fetchone(self):
        if not self._fetchone:
            return None
        return self._fetchone.pop(0)

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


def test_calculate_bonuses_fallback():
    # Unit without helper -> fallback 0
    class U:
        pass

    assert nations.calculate_bonuses({}, {}, U()) == 0


def test_economy_get_particular_resources_money_and_resource(monkeypatch):
    fake_cursor = FakeCursor(fetchone_rows=[(100,), (5,)])
    # Provide a fake psycopg2 module with connect
    import types

    fake_pg = types.SimpleNamespace()
    fake_pg.connect = lambda *a, **kw: FakeConn(fake_cursor)
    monkeypatch.setattr(nations, "psycopg2", fake_pg)

    eco = nations.Economy(1)
    res = eco.get_particular_resources(["money", "steel"])
    assert res == {"money": 100, "steel": 5}


def test_economy_get_particular_resources_invalid(monkeypatch):
    fake_cursor = FakeCursor(fetchone_rows=[(1,)])
    import types

    fake_pg = types.SimpleNamespace()
    fake_pg.connect = lambda *a, **kw: FakeConn(fake_cursor)
    monkeypatch.setattr(nations, "psycopg2", fake_pg)

    eco = nations.Economy(1)
    res = eco.get_particular_resources(["bad_resource"])
    assert res == {}


def test_nation_send_news_calls_db(monkeypatch):
    fake_cursor = FakeCursor()
    conn = FakeConn(fake_cursor)
    import types

    fake_pg = types.SimpleNamespace()
    fake_pg.connect = lambda *a, **kw: conn
    monkeypatch.setattr(nations, "psycopg2", fake_pg)

    nations.Nation.send_news(3, "hello")
    assert any("INSERT INTO news" in q for q, _ in fake_cursor.executed)


def test_military_infrastructure_damage_destroys_and_updates(monkeypatch):
    # Build a particular_infra with 2 libraries and 1 hospital
    infra = {"libraries": 2, "hospitals": 1}
    # Provide a FakeCursor to capture updates
    fake_cursor = FakeCursor()
    conn = FakeConn(fake_cursor)

    # Monkeypatch database.get_db_connection to use our fake conn
    import database

    class FakeCtx:
        def __init__(self, conn):
            self._conn = conn

        def __enter__(self):
            return self._conn

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(database, "get_db_connection", lambda *a, **kw: FakeCtx(conn))

    # Make random deterministic so we pick first building
    monkeypatch.setattr(random, "randint", lambda a, b: 0)

    effects = nations.Military.infrastructure_damage(1500, infra, 10)
    # Should have at least one destroyed building
    assert isinstance(effects, dict)
    # Ensure DB execute called for UPDATE proInfra when destroyed
    assert any("UPDATE proInfra SET" in q for q, _ in fake_cursor.executed)
