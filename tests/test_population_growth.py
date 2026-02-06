class FakeCursor:
    def __init__(self, fetchall_return=None, fetchone_returns=None):
        self._fetchall = fetchall_return or []
        self._fetchone_returns = list(fetchone_returns or [])
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((query, params))

    def fetchone(self):
        if self._fetchone_returns:
            return self._fetchone_returns.pop(0)
        # Default: return True for advisory lock queries
        return (True,)

    def fetchall(self):
        # Support queued fetchall returns for multiple queries in a single run
        if hasattr(self, "_queue") and self._queue:
            return self._queue.pop(0)
        return self._fetchall

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self, cursor_factory=None):
        return self._cursor

    def commit(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_population_growth_updates(monkeypatch):
    import tasks

    # Create two provinces rows as RealDictCursor would return (dict-like)
    provinces = [
        {
            "id": 10,
            "userid": 1,
            "population": 1000,
            "citycount": 1,
            "land": 0,
            "happiness": 50,
            "pollution": 50,
            "productivity": 1,
        },
        {
            "id": 11,
            "userid": 1,
            "population": 2000,
            "citycount": 0,
            "land": 0,
            "happiness": 50,
            "pollution": 50,
            "productivity": 1,
        },
    ]

    # Prepare dbdict to return provinces first, then resources second
    # Also prepare fetchone returns for:
    # 1) advisory lock: (True,)
    # 2) task_runs last_run: (None,) to skip rate limit check
    dbdict = FakeCursor(fetchone_returns=[(True,), (None,)])
    dbdict._queue = [provinces, [{"id": 1, "rations": 100}]]
    conn = FakeConn(dbdict)

    # monkeypatch connection used in population_growth
    import database as _database

    monkeypatch.setattr(_database, "get_db_connection", lambda: conn)

    recorded = {"calls": []}

    def fake_execute_batch(db_cursor, query, seq, **kwargs):
        recorded["calls"].append((query, list(seq)))

    import psycopg2.extras as extras

    monkeypatch.setattr(extras, "execute_batch", fake_execute_batch)

    # Run population_growth - should call execute_batch
    # for rations and population updates
    tasks.population_growth()

    assert any(
        "UPDATE provinces SET population=%s WHERE id=%s" in q
        for q, seq in recorded["calls"]
    ) or any(
        "UPDATE resources SET rations=%s WHERE id=%s" in q
        for q, seq in recorded["calls"]
    )
