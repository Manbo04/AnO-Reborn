import tasks
import math


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

    # Make this usable as a context manager returned by get_db_cursor
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_calc_ti_total_population(monkeypatch):
    # Setup: user has consumer_goods=10, and two provinces
    # with populations 100000 and 100000
    consumer_goods = 10
    # resources.fetchone for consumer_goods
    db = FakeCursor(
        fetchone_returns=[(consumer_goods,)],
        fetchall_return=[(100000, 1), (100000, 1)],
    )

    monkeypatch.setattr("database.get_db_cursor", lambda: db)

    # Ensure we reload the module so tests pick up latest edits
    import importlib

    importlib.reload(tasks)

    # Run (use the production function, now corrected)
    income, removed_cg = tasks.calc_ti(1)

    # Expected values:
    # total_population = 200000
    # CONSUMER_GOODS_PER = 80000 -> max_cg = ceil(200000 / 80000) = 3
    import variables

    total_population = 100000 + 100000
    expected_max_cg = math.ceil(total_population / variables.CONSUMER_GOODS_PER)

    # If consumer_goods (10) > expected_max_cg (3) then we should remove expected_max_cg
    assert expected_max_cg == 3
    assert (
        removed_cg == expected_max_cg
    ), f"Expected removed consumer goods to be {expected_max_cg}, got {removed_cg}"


def test_calc_ti_consumer_goods_multiplier(monkeypatch):
    # Setup: user has small consumer goods not enough to cover max
    consumer_goods = 1
    db = FakeCursor(fetchone_returns=[(consumer_goods,)], fetchall_return=[(100000, 1)])
    monkeypatch.setattr("database.get_db_cursor", lambda: db)

    import importlib

    importlib.reload(tasks)

    income, removed_cg = tasks.calc_ti(1)
    # If consumer_goods < max_cg, removed_cg should equal consumer_goods
    assert removed_cg == consumer_goods
