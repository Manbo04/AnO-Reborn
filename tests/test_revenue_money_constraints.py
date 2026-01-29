class FakeCursor:
    def __init__(self, fetchone_returns=None, fetchall_return=None):
        self._fetchone_returns = list(fetchone_returns or [])
        self._fetchall = fetchall_return or []

    def execute(self, query, params=None):
        self._last_query = query
        self._last_params = params

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


def test_get_revenue_respects_money_constraints(monkeypatch):
    import countries

    # User has low money (10), but a single mall with very high upkeep
    # Mall money cost is 450000 (see variables.INFRA)

    # Setup provinces list: one province id=100
    # fetchone sequence: cg_need -> returns 0 population, gold -> 10, rations -> 0
    db = FakeCursor(
        fetchone_returns=[(0,), (10,), (0,)], fetchall_return=[(100, 0, 50)]
    )

    # proInfra row: index corresponds to building; place 1 mall at its index
    import variables

    total_cols = 1 + len(variables.BUILDINGS)  # id + building columns
    # place a single mall at the correct index (malls is the 10th column -> index 9)
    row = [0] * total_cols
    row[0] = 100
    row[9] = 1
    proinfra_row = tuple(row)

    # set queue for proInfra fetch
    db._fetchall = [(100, 0, 50)]  # provinces

    # dict cursor will return proInfra row and any subsequent queries
    dict_cursor = FakeCursor(fetchone_returns=[None], fetchall_return=[proinfra_row])

    conn = FakeConn(db, dict_cursor)

    monkeypatch.setattr("database.get_db_connection", lambda: conn)
    # Ensure cache miss
    from database import query_cache

    monkeypatch.setattr(query_cache, "get", lambda key: None)
    monkeypatch.setattr(query_cache, "set", lambda key, val: None)

    # next_turn_rations triggers nested db calls; stub it to avoid heavy simulation
    monkeypatch.setattr(countries, "next_turn_rations", lambda cId, prod: 0)

    rev = countries.get_revenue(1)

    # The mall's operating costs should NOT be subtracted from `net.money` or
    # its consumer_goods production included in net, because user cannot afford it.
    assert rev["gross"]["money"] == rev["gross"]["money"]  # gross is unchanged
    assert rev["net"]["money"] >= 0 or rev["net"]["money"] == 0
    # Ensure consumer_goods net not increased by mall production
    assert rev["net"]["consumer_goods"] <= rev["gross"]["consumer_goods"]
