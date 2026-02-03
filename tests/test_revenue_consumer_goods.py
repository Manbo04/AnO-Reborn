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


def test_get_revenue_consumer_goods_net_subtracts_citizen_need(monkeypatch):
    """Net consumer goods should be gross - citizen need (population-based),
    not based on tax income consumption from stockpile."""
    import countries
    import variables

    # Province: id=100, land=0, productivity=50, population=1000
    infra_ids = [(100, 0, 50)]

    # db is non-dict cursor used by get_revenue
    # Provide fetchone returns for:
    # 1) any earlier checks
    # 2) rations SELECT in next_turn_rations
    # 3) SUM(population) query for citizen_cg_need calculation
    population = 1000  # This gives citizen_cg_need = ceil(1000 / CONSUMER_GOODS_PER)
    db = FakeCursor(fetchone_returns=[(0,), (0,), (population,)], fetchall_return=[])

    # First fetchall -> provinces (id, land, productivity)
    # Second fetchall -> proInfra row.
    # We include at least 10 entries so 'malls' index maps.
    proinfra_row = [100] + [0] * 8 + [1]  # malls at index 9
    db._queue = [infra_ids, [tuple(proinfra_row)]]

    conn = FakeConn(db, db)

    monkeypatch.setattr("database.get_db_connection", lambda: conn)
    # cg_need is not used for net calculation anymore, but mock it anyway
    monkeypatch.setattr(countries, "cg_need", lambda cid: 0)
    # calc_ti returns (money, cg) - but ti_cg is no longer used for net CG
    monkeypatch.setattr(countries, "calc_ti", lambda cid: (0, 50))

    # Ensure cache miss
    from database import query_cache

    monkeypatch.setattr(query_cache, "get", lambda key: None)
    monkeypatch.setattr(query_cache, "set", lambda key, val: None)

    rev = countries.get_revenue(1)

    # malls produce 30 consumer goods (per variables.INFRA); gross should be 30
    assert rev["gross"]["consumer_goods"] == 30
    # Net consumer goods = gross - citizen_cg_need
    # citizen_cg_need = ceil(population / CONSUMER_GOODS_PER) = ceil(1000 / 1000) = 1
    import math

    expected_citizen_need = math.ceil(population / variables.CONSUMER_GOODS_PER)
    expected_net = 30 - expected_citizen_need  # 30 - 1 = 29
    assert rev["net"]["consumer_goods"] == expected_net
