def test_get_revenue_applies_productivity(monkeypatch):
    import countries

    # Fake DB: one user with one province with 4 lumber_mills and productivity 0
    class FakeCursor:
        def __init__(self):
            # queue for fetchall to simulate sequential fetches
            self._queue = [
                [(258, 0, 0)],  # provinces
                [tuple([258] + [0] * 28 + [4] + [0] * 5)],  # proInfra
            ]
            self.calls = []

        def execute(self, q, p=None):
            self.calls.append((q, p))

        def fetchall(self):
            if self._queue:
                return self._queue.pop(0)
            return []

        def fetchone(self):
            # resources.rations fetch -> 0
            return (0,)

    db = FakeCursor()

    # dbdict not required here; get_revenue uses the main cursor
    # for provinces and proInfra
    dbdict = None

    class FakeConn:
        def __init__(self, db, dbdict):
            self._db = db
            self._dbdict = dbdict

        def cursor(self, cursor_factory=None):
            if cursor_factory:
                return self._dbdict
            return self._db

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("database.get_db_connection", lambda: FakeConn(db, dbdict))
    monkeypatch.setattr("database.query_cache.get", lambda k: None)
    monkeypatch.setattr("database.query_cache.set", lambda k, v: None)

    rev = countries.get_revenue(900)
    # With productivity 0, multiplier = 0.55 -> 4 * 35 * 0.55 = 77
    assert rev["gross"]["lumber"] == 77
