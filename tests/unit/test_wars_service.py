import time

from wars import service


class FakeCursor:
    def __init__(self, fetchall_rows=None, fetchone_rows=None):
        self._fetchall = fetchall_rows or []
        self._fetchone = fetchone_rows or []
        self.executed = []

    def execute(self, query, params=None):
        self.executed.append((query, params))

    def fetchall(self):
        return self._fetchall

    def fetchone(self):
        if not self._fetchone:
            return None
        return self._fetchone.pop(0)


class FakeCtx:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self._cursor

    def __exit__(self, exc_type, exc, tb):
        return False


def test_target_data_uses_influence_and_province_count(monkeypatch):
    fake_cursor = FakeCursor(fetchone_rows=[(5,)])
    monkeypatch.setattr(service, "get_db_cursor", lambda: FakeCtx(fake_cursor))
    monkeypatch.setattr(service, "get_influence", lambda cid: 100)

    data = service.target_data(1)
    assert data["upper"] == 200
    assert data["lower"] == 90
    assert data["province_range"] == 5


def test_update_supply_time_corrupted(monkeypatch):
    future = time.time() + 3600
    fake_cursor = FakeCursor(fetchall_rows=[(10, 20, future)])
    monkeypatch.setattr(service, "get_db_cursor", lambda: FakeCtx(fake_cursor))

    res = service.update_supply(1)
    assert res == "TIME STAMP IS CORRUPTED"


def test_update_supply_adds_supplies(monkeypatch):
    # supply_date 2 hours ago => supply_by_hours = 100
    supply_date = time.time() - (2 * 3600)
    fake_cursor = FakeCursor(
        fetchall_rows=[(50, 60, supply_date)], fetchone_rows=[(11, 22)]
    )
    monkeypatch.setattr(service, "get_db_cursor", lambda: FakeCtx(fake_cursor))

    # Mock Nation.get_upgrades to return small values
    class FakeNation:
        @staticmethod
        def get_upgrades(key, uid):
            return {"a": 5} if uid == 11 else {"b": 2}

    monkeypatch.setattr(service, "Nation", FakeNation)

    service.update_supply(1)

    # Check that UPDATE for attacker and defender supplies were executed
    queries = [q for q, _ in fake_cursor.executed]
    assert any("UPDATE wars SET attacker_supplies" in q for q in queries)
    assert any("UPDATE wars SET defender_supplies" in q for q in queries)
