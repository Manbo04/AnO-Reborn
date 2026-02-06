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
    population = 1000  # This gives citizen_cg_need = ceil(1000 / CONSUMER_GOODS_PER)

    # db is non-dict cursor used by get_revenue
    # Provide fetchone returns in order:
    # 1) gold: for money constraints check
    # 2) rations: SELECT rations FROM resources
    # 3) consumer_goods: for inlined calc_ti (SELECT consumer_goods FROM resources)
    # 4) policies: for inlined calc_ti (SELECT education FROM policies)
    # 5) SUM(population) query for citizen_cg_need calculation
    # 6) rations for next_turn_rations
    # 7+) various other queries in next_turn_rations
    db = FakeCursor(
        fetchone_returns=[
            (100000,),  # gold - sufficient to operate buildings
            (0,),  # rations
            (0,),  # consumer_goods for calc_ti
            (None,),  # policies (no education)
            (population,),  # SUM(population) for citizen_cg_need
            (0,),  # rations for next_turn_rations
            (population,),  # population for next_turn_rations
        ],
        fetchall_return=[],
    )

    # Fetchall queue:
    # 1) provinces (id, land, productivity)
    # 2) proInfra row
    # 3) ti_provinces (population, land) for inlined calc_ti
    # 4) provinces population for next_turn_rations
    proinfra_row = [100] + [0] * 8 + [1]  # malls at index 9
    db._queue = [
        infra_ids,  # provinces
        [tuple(proinfra_row)],  # proInfra
        [(population, 0)],  # ti_provinces for calc_ti
        [(population,)],  # provinces population for next_turn_rations
    ]

    conn = FakeConn(db, db)

    monkeypatch.setattr("database.get_db_connection", lambda: conn)
    # cg_need is not used for net calculation anymore, but mock it anyway
    monkeypatch.setattr(countries, "cg_need", lambda cid: 0)
    # calc_ti is now inlined in get_revenue, no need to monkeypatch

    # Ensure cache miss
    from database import query_cache

    monkeypatch.setattr(query_cache, "get", lambda key: None)
    monkeypatch.setattr(query_cache, "set", lambda key, val, ttl_seconds=None: None)

    rev = countries.get_revenue(1)

    # malls produce 30 consumer goods (per variables.INFRA); gross should be 30
    assert rev["gross"]["consumer_goods"] == 30
    # Net consumer goods = gross - citizen_cg_need
    # citizen_cg_need = ceil(population / CONSUMER_GOODS_PER) = ceil(1000 / 1000) = 1
    import math

    expected_citizen_need = math.ceil(population / variables.CONSUMER_GOODS_PER)
    expected_net = 30 - expected_citizen_need  # 30 - 1 = 29
    assert rev["net"]["consumer_goods"] == expected_net
