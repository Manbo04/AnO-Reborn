import tasks


class FakeCursor:
    def __init__(self, fetchall_return=None, fetchone_returns=None):
        self._fetchall = fetchall_return or []
        self._fetchone_returns = list(fetchone_returns or [])
        self.execute_calls = []

    def execute(self, query, params=None):
        self.execute_calls.append((query, params))

    def fetchall(self):
        return self._fetchall

    def fetchone(self):
        if self._fetchone_returns:
            return self._fetchone_returns.pop(0)
        return None


class FakeConn:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self, cursor_factory=None):
        return self.db


def test_tax_income_uses_positive_cg(monkeypatch):
    # Prepare one user id
    user_rows = [(1,)]

    # For SELECT gold FROM stats -> return (1000,)
    # Note: order of fetchone calls in tax_income: SELECT gold FROM stats -> fetchone
    # Later other calls may occur
    db = FakeCursor(fetchall_return=user_rows, fetchone_returns=[(1000,)])

    conn = FakeConn(db)
    monkeypatch.setattr("database.get_db_connection", lambda: conn)

    # Patch calc_ti to return (money, consumer_goods) where we expect
    # consumer_goods removal of 3
    monkeypatch.setattr(tasks, "calc_ti", lambda uid: (100, 3))

    recorded = {"calls": []}

    # Monkeypatch execute_batch to capture how it's invoked
    def fake_execute_batch(db_cursor, query, seq):
        recorded["calls"].append((query, list(seq)))

    import psycopg2.extras as extras

    monkeypatch.setattr(extras, "execute_batch", fake_execute_batch)

    # Reload tasks module to ensure latest code is used, then run
    import importlib

    importlib.reload(tasks)

    tasks.tax_income()

    # Validate: one of the calls should be the consumer goods update with (3, 1)
    # Validate presence of call that updates consumer goods for the user
    expected_q = "UPDATE resources SET consumer_goods=consumer_goods-%s WHERE id=%s"
    cg_called = any((expected_q in q and (3, 1) in seq) for q, seq in recorded["calls"])
    assert cg_called, "Consumer goods update not recorded"
