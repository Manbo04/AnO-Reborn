import importlib
import tasks


# Reuse the fake DB cursor pattern from existing tests
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
        return self._fetchall

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_gas_stations_increase_tax(monkeypatch):
    """Ensure that adding gas stations (more consumer_goods)
    does not reduce tax income.
    """

    # Setup a user with one province population 240000 and no initial consumer_goods
    # Simulate resources.fetchone -> consumer_goods (first call in calc_ti)
    # Simulate provinces.fetchall -> [(population, land), ...]

    # Scenario A: no gas stations -> consumer_goods = 0
    db_a = FakeCursor(fetchone_returns=[(0,)], fetchall_return=[(240000, 1)])
    monkeypatch.setattr("database.get_db_cursor", lambda: db_a)
    importlib.reload(tasks)
    income_a, removed_a = tasks.calc_ti(1)

    # Scenario B: enough gas stations to add 36 consumer_goods (3 * 12)
    db_b = FakeCursor(fetchone_returns=[(36,)], fetchall_return=[(240000, 1)])
    monkeypatch.setattr("database.get_db_cursor", lambda: db_b)
    importlib.reload(tasks)
    income_b, removed_b = tasks.calc_ti(1)

    assert (
        income_b >= income_a
    ), f"Tax income decreased after adding gas stations: {income_a} -> {income_b}"


def test_gas_stations_partial_cover(monkeypatch):
    """Small consumer_goods should maintain non-negative delta in tax income."""
    # population 240000 -> max_cg = ceil(240000/80000)=3
    # If consumer_goods = 1 (partial), income should not be less than with 0

    db0 = FakeCursor(fetchone_returns=[(0,)], fetchall_return=[(240000, 1)])
    db1 = FakeCursor(fetchone_returns=[(1,)], fetchall_return=[(240000, 1)])

    monkeypatch.setattr("database.get_db_cursor", lambda: db0)
    importlib.reload(tasks)
    income0, _ = tasks.calc_ti(1)

    monkeypatch.setattr("database.get_db_cursor", lambda: db1)
    importlib.reload(tasks)
    income1, _ = tasks.calc_ti(1)

    assert income1 >= income0, f"Tax income decreased: {income0} -> {income1}"
