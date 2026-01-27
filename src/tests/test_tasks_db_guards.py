# Local-only tests: use simple mocks to avoid touching the real DB

from src import tasks


class DummyCursor:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.execs = []

    def execute(self, sql, params=None):
        self.execs.append((sql, params))

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None

    def fetchall(self):
        return []


class DummyCtx:
    def __init__(self, cursor):
        self.cursor = cursor

    def __enter__(self):
        return self.cursor

    def __exit__(self, exc_type, exc, tb):
        return False


def test_calc_pg_handles_missing_population(monkeypatch):
    """If SELECT population returns None, calc_pg should not raise and
    should return a (rations_delta, fullPop) tuple."""

    dummy = DummyCursor(rows=[None])

    # Patch the database helpers that calc_pg imports at runtime
    from src import database

    monkeypatch.setattr(
        database, "get_db_cursor", lambda *args, **kwargs: DummyCtx(dummy)
    )
    # fetchone_first is used later to read owner/policies — make it return defaults
    monkeypatch.setattr(database, "fetchone_first", lambda db, default=None: default)

    # No exception should be raised and return types should be ints
    rations_delta, fullPop = tasks.calc_pg(1, 0)
    assert isinstance(rations_delta, int)
    assert isinstance(fullPop, int)


def test_safe_update_productivity_clamps_overflow():
    """Ensure _safe_update_productivity clamps big values instead of writing
    an out-of-range integer to the DB."""

    big_value = 3_000_000_000  # bigger than 32-bit signed max
    dummy = DummyCursor(rows=[[big_value]])

    # Call the helper directly
    tasks._safe_update_productivity(dummy, 6, 1.05)

    # Last execute should be an UPDATE and the value should be clamped
    last_sql, last_params = dummy.execs[-1]
    assert "UPDATE provinces SET productivity" in last_sql
    new_val = last_params[0]
    assert isinstance(new_val, int)
    assert new_val <= tasks.MAX_INT_32
