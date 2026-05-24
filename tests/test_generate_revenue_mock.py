import tasks


def make_conn():
    class FakeCursor:
        def __init__(self, fetchall_return=None, fetchone_returns=None):
            self.calls = []
            self._fetchall = fetchall_return or []
            self._fetchone_returns = list(fetchone_returns or [])

        def execute(self, query, params=None):
            self.calls.append((query, params))
            if "SELECT education FROM policies" in query:
                raise Exception("no policies")

        def fetchall(self):
            return self._fetchall

        def fetchone(self):
            if self._fetchone_returns:
                return self._fetchone_returns.pop(0)
            return None

    infra_ids = [(1, 42, 100, 50)]

    db = FakeCursor(
        fetchall_return=infra_ids,
        fetchone_returns=[(0,), (infra_ids,)],
    )

    dbdict = FakeCursor(
        fetchall_return=[],
        fetchone_returns=[],
    )

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def cursor(self, cursor_factory=None):
            return dbdict if cursor_factory is not None else db

        def commit(self):
            pass

        def rollback(self):
            pass

    return FakeConn(), db, dbdict


def test_generate_revenue_monkeypatch(monkeypatch):
    conn, db, dbdict = make_conn()
    monkeypatch.setattr("database.get_db_connection", lambda: conn)
    monkeypatch.setattr(
        "tasks.try_pg_advisory_lock",
        lambda _c, _i, _l: True,
    )

    tasks.generate_province_revenue()

    executed_queries = [q for q, _ in db.calls]
    energy_update_found = any(
        ("UPDATE provinces SET" in q and "energy" in q) for q in executed_queries
    )
    assert energy_update_found, "Expected energy reset UPDATE to be executed"

    dict_queries = [q for q, _ in dbdict.calls]
    assert any(
        "user_tech" in q and "tech_dictionary" in q for q in dict_queries
    ), "Expected normalized user_tech preload"
    assert any(
        "user_buildings" in q and "building_dictionary" in q for q in dict_queries
    ), "Expected normalized user_buildings preload"


def test_generate_revenue_handles_missing_advancedmachinery(monkeypatch):
    conn, db, dbdict = make_conn()
    monkeypatch.setattr("database.get_db_connection", lambda: conn)
    monkeypatch.setattr(
        "tasks.try_pg_advisory_lock",
        lambda _c, _i, _l: True,
    )

    tasks.generate_province_revenue()
