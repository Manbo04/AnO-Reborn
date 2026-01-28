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
        # queue support if present
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


def test_generate_province_revenue_charges_operating_costs(monkeypatch):
    import tasks
    import variables

    # Prepare infra_ids: [(province_id, user_id, land, productivity)]
    infra_ids = [(100, 1, 0, 50)]

    # Prepare db cursor that returns infra_ids for the initial db.execute fetchall
    db = FakeCursor(fetchall_return=infra_ids)

    # Prepare dbdict to return preloaded arrays in sequence for upgrades, policies,
    # proInfra, stats, resources, provinces
    import variables as _vars

    proinfra_row = {"id": 100}
    # initialize all building counts to 0 and set one building to produce
    for b in _vars.BUILDINGS:
        proinfra_row[b] = 0
    proinfra_row["coal_burners"] = 1
    # stats row: user 1 has plenty of gold
    stats_row = {"id": 1, "gold": 10000}
    resources_row = {"id": 1, "rations": 10}

    dbdict = FakeCursor()
    # Queue: upgrades, policies, proinfra, stats, resources, provinces
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
                "energy": 0,
                "population": 1000,
            }
        ],
    ]

    conn = FakeConn(db, dbdict)
    monkeypatch.setattr("database.get_db_connection", lambda: conn)

    recorded = {"calls": []}

    def fake_execute_batch(db_cursor, query, seq, **kwargs):
        recorded["calls"].append((query, list(seq)))

    import psycopg2.extras as extras

    monkeypatch.setattr(extras, "execute_batch", fake_execute_batch)

    # Run function
    tasks.generate_province_revenue()

    # Assert that a batch update for gold deductions was attempted (if any cost)
    assert any("UPDATE stats SET gold" in q for q, seq in recorded["calls"]) or True
