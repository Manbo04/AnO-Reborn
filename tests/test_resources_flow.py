# Lightweight fakes similar to other tests
class FakeCursor:
    def __init__(self, fetchone_returns=None, fetchall_return=None):
        self._fetchone_returns = list(fetchone_returns or [])
        self._fetchall = fetchall_return or []
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((query, params))

    def fetchone(self):
        if self._fetchone_returns:
            return self._fetchone_returns.pop(0)
        return None

    def fetchall(self):
        return self._fetchall

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False

    def cursor(self, cursor_factory=None):
        # ignore cursor_factory for fakes
        return self._cursor

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def commit(self):
        self.committed = True


def test_give_resource_money_bank_to_user(monkeypatch):
    from market import give_resource

    db = FakeCursor()
    conn = FakeConn(db)
    import market as _market

    monkeypatch.setattr(_market, "get_db_connection", lambda: conn)

    # Bank giving money to user should call UPDATE stats SET gold=gold+%s
    res = give_resource("bank", 5, "money", 100)
    assert res is True
    assert any("UPDATE stats SET gold=gold+%s" in q for q, p in db.calls)


def test_give_resource_money_user_insufficient(monkeypatch):
    from market import give_resource

    # Simulate insufficient funds (UPDATE RETURNING fails)
    db = FakeCursor(fetchone_returns=[None])
    conn = FakeConn(db)
    import market as _market

    monkeypatch.setattr(_market, "get_db_connection", lambda: conn)

    res = give_resource(1, 2, "money", 100)
    assert isinstance(res, str)
    assert "Giver doesn't have enough" in res


def test_give_resource_non_money_transfer(monkeypatch):
    from market import give_resource

    # Simulate giver has 20 of resource
    db = FakeCursor(fetchone_returns=[(20,)])
    conn = FakeConn(db)
    import market as _market

    monkeypatch.setattr(_market, "get_db_connection", lambda: conn)

    res = give_resource(1, 2, "coal", 5)
    assert res is True

    # ensure an UPDATE to resources for coal happened (either +/-)
    assert any(
        ("UPDATE resources SET" in q and "coal" in q and ("-" in q or "+" in q))
        for q, p in db.calls
    )


def test_tax_income_clamps_consumer_goods(monkeypatch):
    import tasks

    # Prepare one user with id 1
    users = [(1,)]

    # resources select: return consumer_goods=1
    db = FakeCursor(fetchone_returns=[(1000,)], fetchall_return=users)

    # Fake connection that captures execute_batch calls by using a monkeypatch
    conn = FakeConn(db)
    monkeypatch.setattr("database.get_db_connection", lambda: conn)

    recorded = {"calls": []}

    def fake_execute_batch(db_cursor, query, seq, **kwargs):
        recorded["calls"].append((query, list(seq)))

    import psycopg2.extras as extras

    monkeypatch.setattr(extras, "execute_batch", fake_execute_batch)

    # Stub calc_ti to return income and removed cg
    monkeypatch.setattr(tasks, "calc_ti", lambda uid: (100, 3))

    tasks.tax_income()

    expected_q = (
        "UPDATE resources SET consumer_goods=GREATEST(consumer_goods-%s, 0) WHERE id=%s"
    )
    cg_called = any(expected_q in q and (3, 1) in seq for q, seq in recorded["calls"])
    assert cg_called, "Expected consumer goods clamped update to be called"
