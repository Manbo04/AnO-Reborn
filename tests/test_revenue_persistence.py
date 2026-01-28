def test_generate_province_revenue_persists_coal_and_lumber(monkeypatch):
    import tasks
    import variables

    # Prepare infra_ids: [(province_id, user_id, land, productivity)]
    infra_ids = [(200, 2, 0, 50)]

    # db is used for the initial select and batch updates
    db = type(
        "C",
        (),
        {"calls": [], "_fetchall": infra_ids, "_fetchone_returns": []},
    )()

    def db_execute(q, params=None):
        db.calls.append((q, params))

    def db_fetchall():
        return db._fetchall

    def db_fetchone():
        if hasattr(db, "_fetchone_returns") and db._fetchone_returns:
            return db._fetchone_returns.pop(0)
        return None

    # Minimal mogrify so psycopg2.extras.execute_batch can call it
    def db_mogrify(sql, args):
        # return bytes similar to real mogrify
        try:
            return sql.encode()
        except Exception:
            return b""

    # Attach methods
    db.execute = db_execute
    db.fetchall = db_fetchall
    db.fetchone = db_fetchone
    db.mogrify = db_mogrify

    # dbdict returns queued rows for the queries we make
    class FakeCursor:
        def __init__(self):
            self._queue = []
            self.calls = []

        def execute(self, q, params=None):
            self.calls.append((q, params))

        def fetchone(self):
            return None

        def fetchall(self):
            return self._queue.pop(0) if self._queue else []

    dbdict = FakeCursor()

    # Build proInfra row with one coal_mine and one lumber_mill
    proinfra_row = {"id": 200}
    for b in variables.BUILDINGS:
        proinfra_row[b] = 0
    proinfra_row["coal_mines"] = 1
    proinfra_row["lumber_mills"] = 1

    stats_row = {"id": 2, "gold": 100000}
    resources_row = {"id": 2, "rations": 10}
    province_row = {
        "id": 200,
        "happiness": 50,
        "productivity": 50,
        "pollution": 0,
        "consumer_spending": 50,
        "energy": 0,
        "population": 100,
    }

    # Order: upgrades, policies, proInfra, stats, resources, provinces
    dbdict._queue = [
        [],
        [],
        [proinfra_row],
        [stats_row],
        [resources_row],
        [province_row],
    ]

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

        def commit(self):
            pass

        def rollback(self):
            # No-op for tests
            pass

    conn = FakeConn(db, dbdict)
    monkeypatch.setattr("database.get_db_connection", lambda: conn)

    # Run revenue
    tasks.generate_province_revenue()

    # Find any UPDATE resources SET ... that includes coal or lumber
    resource_updates = []
    for q, _ in db.calls:
        if not q:
            continue
        if isinstance(q, bytes):
            q_str = q.decode(errors="ignore")
        else:
            q_str = str(q)
        if q_str.startswith("UPDATE resources SET"):
            resource_updates.append(q_str)

    assert any("coal" in q for q in resource_updates), "coal not persisted"
    assert any("lumber" in q for q in resource_updates), "lumber not persisted"
