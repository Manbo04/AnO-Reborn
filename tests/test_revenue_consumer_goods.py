class FakeCursor:
    def __init__(self, fetchone_returns=None, fetchall_return=None):
        self._fetchone_returns = list(fetchone_returns or [])
        self._fetchall = fetchall_return or []
        self._queue = []
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((query, params))

    def fetchone(self):
        if self._fetchone_returns:
            return self._fetchone_returns.pop(0)
        return None

    def fetchall(self):
        if hasattr(self, "_queue") and self._queue:
            return self._queue.pop(0)
        return self._fetchall

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeConn:
    def __init__(self, db_cursor, dict_cursor=None):
        self._db = db_cursor
        self._dbdict = dict_cursor or db_cursor

    def cursor(self, cursor_factory=None):
        if cursor_factory:
            return self._dbdict
        return self._db

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def commit(self):
        pass


def test_get_revenue_consumer_goods_net_subtracts_taxes(monkeypatch):
    """If tax income consumes consumer goods, net consumer goods should
    be reduced (gross - consumed), not increased."""
    import countries

    # Province: id=100, land=0, productivity=50
    infra_ids = [(100, 0, 50)]

    # db is non-dict cursor used by get_revenue
    # Provide two fetchone returns to satisfy any earlier checks and the
    # rations SELECT in next_turn_rations
    db = FakeCursor(fetchone_returns=[(0,), (0,)], fetchall_return=[])

    # First fetchall -> provinces (id, land, productivity)
    # Second fetchall -> proInfra row.
    # We include at least 10 entries so 'malls' index maps.
    proinfra_row = [100] + [0] * 8 + [1]  # malls at index 9
    db._queue = [infra_ids, [tuple(proinfra_row)]]

    conn = FakeConn(db, db)

    monkeypatch.setattr("database.get_db_connection", lambda: conn)
    # Avoid cg_need DB calls
    monkeypatch.setattr(countries, "cg_need", lambda cid: 0)
    # Simulate tax income consuming 50 consumer goods
    monkeypatch.setattr(countries, "calc_ti", lambda cid: (0, 50))

    # Ensure cache miss
    from database import query_cache

    monkeypatch.setattr(query_cache, "get", lambda key: None)
    monkeypatch.setattr(query_cache, "set", lambda key, val: None)

    rev = countries.get_revenue(1)

    # malls produce 30 consumer goods (per variables.INFRA); gross should be 30
    assert rev["gross"]["consumer_goods"] == 30
    # Net should be production (30) minus consumed (50) == -20
    assert rev["net"]["consumer_goods"] == -20
