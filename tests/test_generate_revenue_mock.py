import tasks


def make_conn():
    # A very small fake DB cursor
    # that records execute calls and returns preset fetchall/fetchone
    class FakeCursor:
        def __init__(self, fetchall_return=None, fetchone_returns=None):
            self.calls = []
            self._fetchall = fetchall_return or []
            self._fetchone_returns = list(fetchone_returns or [])

        def execute(self, query, params=None):
            # record the call
            self.calls.append((query, params))
            # Simulate missing policies
            # by raising on that specific query so the code falls back to []
            if "SELECT education FROM policies" in query:
                raise Exception("no policies")

        def fetchall(self):
            return self._fetchall

        def fetchone(self):
            if self._fetchone_returns:
                return self._fetchone_returns.pop(0)
            return None

    infra_ids = [(1, 42, 100, 50)]

    # db is the normal cursor used for SELECT/UPDATE etc
    db = FakeCursor(fetchall_return=infra_ids, fetchone_returns=[])

    # upgrades and proInfra (units) are returned via the RealDictCursor (dbdict)
    upgrades = {
        "cheapermaterials": False,
        "automationintegration": False,
        "largerforges": False,
        "nationalhealthinstitution": False,
        "onlineshopping": False,
        "betterengineering": False,
        "highspeedrail": False,
    }

    # Create a proInfra units dict with zero amounts to avoid inner-side effects
    pro_infra = {unit: 0 for unit in tasks.variables.BUILDINGS}

    dbdict = FakeCursor(fetchall_return=None, fetchone_returns=[upgrades, pro_infra])

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def cursor(self, cursor_factory=None):
            # If a cursor_factory is provided (RealDictCursor), return dbdict
            # Otherwise return the standard cursor
            return dbdict if cursor_factory is not None else db

        def commit(self):
            pass

        def rollback(self):
            pass

    return FakeConn(), db, dbdict


def test_generate_revenue_monkeypatch(monkeypatch):
    conn, db, dbdict = make_conn()
    # Patch database.get_db_connection used in generate_province_revenue
    monkeypatch.setattr("database.get_db_connection", lambda: conn)

    # Call the function under test.
    # It should run without touching a real DB or creating accounts.
    tasks.generate_province_revenue()

    # Verify that at least the energy reset was attempted for the province
    executed_queries = [q for q, _ in db.calls]
    # Expect an UPDATE that includes energy as one of the updated fields
    energy_update_found = any(
        ("UPDATE provinces SET" in q and "energy" in q) for q in executed_queries
    )
    assert energy_update_found, "Expected energy reset UPDATE to be executed"

    # Verify we fetched upgrades and proInfra via the dict cursor
    dict_queries = [q for q, _ in dbdict.calls]
    upgrades_select_found = any("SELECT * FROM upgrades" in q for q in dict_queries)
    assert upgrades_select_found, "Expected upgrades SELECT"
    proinfra_select_found = any("SELECT * FROM proInfra" in q for q in dict_queries)
    assert proinfra_select_found, "Expected proInfra SELECT"


def test_generate_revenue_handles_missing_advancedmachinery(monkeypatch):
    # Ensure that missing 'advancedmachinery' in upgrades does not raise
    conn, db, dbdict = make_conn()

    # Create upgrades without 'advancedmachinery' key
    upgrades = {
        "cheapermaterials": False,
        "automationintegration": False,
        "largerforges": False,
        "nationalhealthinstitution": False,
        "onlineshopping": False,
        "betterengineering": False,
        "highspeedrail": False,
    }

    # Ensure pro_infra has farms present to trigger farms code path
    pro_infra = {unit: 0 for unit in tasks.variables.BUILDINGS}
    pro_infra["farms"] = 1

    dbdict._fetchone_returns = [upgrades, pro_infra]
    monkeypatch.setattr("database.get_db_connection", lambda: conn)

    # Should not raise
    tasks.generate_province_revenue()

    # Confirm an UPDATE was attempted (as in the other test)
    executed_queries = [q for q, _ in db.calls]
    energy_update_found = any(
        ("UPDATE provinces SET" in q and "energy" in q) for q in executed_queries
    )
    assert energy_update_found, "Expected energy reset UPDATE to be executed"
