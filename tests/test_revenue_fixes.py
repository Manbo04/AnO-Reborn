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


def test_get_revenue_does_not_mutate_variables_resources(monkeypatch):
    import countries
    import variables

    original = list(variables.RESOURCES)

    # Prepare fake DB to satisfy minimal queries in get_revenue
    # Sequence of fetches: cg_need -> returns 0 population; provinces list -> empty
    # Return rations as 0 as well
    # Provide enough fetchone return values for nested calls.
    # (cg_need, rations, next_turn_rations)
    db = FakeCursor(fetchone_returns=[(0,), (0,), (0,)], fetchall_return=[])
    dbdict = FakeCursor(fetchone_returns=[None], fetchall_return=[])
    conn = FakeConn(db, dbdict)

    monkeypatch.setattr("database.get_db_connection", lambda: conn)
    # Make calc_ti cheap and deterministic
    monkeypatch.setattr("countries.calc_ti", lambda cId: (0, 0))

    # Ensure cache miss
    from database import query_cache

    monkeypatch.setattr(query_cache, "get", lambda key: None)
    monkeypatch.setattr(query_cache, "set", lambda key, val: None)

    countries.get_revenue(1)

    assert variables.RESOURCES == original


def test_generate_province_revenue_resets_energy(monkeypatch):
    import tasks

    # Infra ids: (province_id, user_id, land, productivity)
    infra_ids = [(100, 1, 0, 50)]

    # db (non-dict cursor) is used for the initial select and the UPDATE energy
    db = FakeCursor(fetchall_return=infra_ids)

    # dbdict returns preloaded rows for multiple queries
    dbdict = FakeCursor()
    proinfra_row = {"id": 100}
    # set all buildings 0 so we still exercise the energy reset
    import variables as _vars

    for b in _vars.BUILDINGS:
        proinfra_row[b] = 0

    stats_row = {"id": 1, "gold": 1000}
    resources_row = {"id": 1, "rations": 10}

    dbdict._queue = [
        [],
        [],
        [proinfra_row],
        [stats_row],
        [resources_row],
        [
            {
                "id": 100,
                "happiness": 50,
                "productivity": 50,
                "pollution": 0,
                "consumer_spending": 50,
                "energy": 5,
                "population": 1000,
            }
        ],
    ]

    conn = FakeConn(db, dbdict)
    monkeypatch.setattr("database.get_db_connection", lambda: conn)

    # Run function
    tasks.generate_province_revenue()

    # Assert that an UPDATE to provinces (including `energy`) was executed
    assert any(
        call[0] and "UPDATE provinces SET" in call[0] and "energy" in call[0]
        for call in db.calls
    )
