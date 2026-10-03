import pytest
from unittest.mock import MagicMock, patch
import app_core.game_ticks.taxes as taxes


class FakeCursor:
    def __init__(self, fetchall_map=None, fetchone_returns=None):
        self.fetchall_map = fetchall_map or {}
        self.fetchone_returns = list(fetchone_returns or [])
        self.execute_calls = []

    def execute(self, query, params=None):
        self.execute_calls.append((query, params))

    def fetchone(self):
        if self.fetchone_returns:
            return self.fetchone_returns.pop(0)
        return None

    def fetchall(self):
        if self.execute_calls:
            last_sql = self.execute_calls[-1][0].strip().lower()
            for key, val in self.fetchall_map.items():
                if key in last_sql:
                    return val
        return []


class FakeConn:
    def __init__(self, db, dbdict):
        self.db = db
        self.dbdict = dbdict

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self, cursor_factory=None):
        if cursor_factory:
            return self.dbdict
        return self.db

    def commit(self):
        pass

    def rollback(self):
        pass


@pytest.mark.no_server
def test_tax_income_resets_cursor_to_zero_on_final_chunk(monkeypatch):
    """Verify that when tax_income processes all users, it resets task_cursors.tax_income to 0
    so the next hourly run starts fresh from the beginning and never skips an hour.
    """
    users = [(1,), (2,)]
    db = FakeCursor(
        fetchall_map={
            "select id from users": users,
            "from provinces": [(1, 1000, 10, 50, 50, 50, 10, 1, 0, 10), (2, 2000, 20, 50, 50, 50, 20, 2, 0, 10)],
        },
        fetchone_returns=[None, (0,), (1,)]  # task_runs last_run, task_cursors last_id, cg resource_id
    )
    dbdict = FakeCursor(
        fetchall_map={
            "select id, gold from stats": [{"id": 1, "gold": 100}, {"id": 2, "gold": 200}],
            "from provinces": [(1, 1000, 10, 50, 50, 50, 10, 1, 0, 10), (2, 2000, 20, 50, 50, 50, 20, 2, 0, 10)],
        }
    )
    conn = FakeConn(db, dbdict)
    monkeypatch.setattr("database.get_db_connection", lambda *a, **k: conn)
    monkeypatch.setattr("database.get_coalition_members_table", lambda: None)
    monkeypatch.setattr("app_core.game_ticks.taxes.try_pg_advisory_lock", lambda *a, **k: True)
    monkeypatch.setattr("app_core.game_ticks.taxes.release_pg_advisory_lock", lambda *a, **k: None)
    monkeypatch.setattr("app_core.game_ticks.taxes.should_skip_task", lambda *a, **k: False)

    recorded_batches = []
    def fake_execute_batch(cursor, query, seq, **kwargs):
        recorded_batches.append((query, list(seq)))

    import psycopg2.extras as extras
    monkeypatch.setattr(extras, "execute_batch", fake_execute_batch)

    taxes.tax_income()

    cursor_updates = [
        (q, p) for q, p in db.execute_calls
        if "update task_cursors" in str(q).lower()
    ]
    assert cursor_updates, "Expected an UPDATE task_cursors call"
    last_update_sql, last_update_params = cursor_updates[-1]
    assert last_update_params == (0, "tax_income"), f"Expected cursor to be reset to 0, got {last_update_params}"


@pytest.mark.no_server
def test_tax_income_handles_legacy_stale_cursor_without_premature_commit(monkeypatch):
    """Verify that when task_cursors starts at the max user id (e.g. 213 from previous run),
    tax_income detects empty chunk, resets cursor to 0 WITHOUT dropping the transaction,
    re-fetches from beginning, and successfully processes all users.
    """
    users = [(1,), (2,)]
    user_calls = 0
    class DynamicCursor(FakeCursor):
        def fetchall(self):
            nonlocal user_calls
            if self.execute_calls:
                last_sql = self.execute_calls[-1][0].strip().lower()
                if "select id from users" in last_sql:
                    user_calls += 1
                    if user_calls == 1:
                        return []  # empty chunk for id > 213
                    return users  # re-fetch returns users
            return super().fetchall()

    db = DynamicCursor(
        fetchall_map={
            "from provinces": [(1, 1000, 10, 50, 50, 50, 10, 1, 0, 10), (2, 2000, 20, 50, 50, 50, 20, 2, 0, 10)],
        },
        fetchone_returns=[None, (213,), (1,)]  # task_runs last_run, task_cursors last_id=213, cg resource_id
    )
    dbdict = FakeCursor(
        fetchall_map={
            "select id, gold from stats": [{"id": 1, "gold": 100}, {"id": 2, "gold": 200}],
            "from provinces": [(1, 1000, 10, 50, 50, 50, 10, 1, 0, 10), (2, 2000, 20, 50, 50, 50, 20, 2, 0, 10)],
        }
    )
    conn = FakeConn(db, dbdict)
    monkeypatch.setattr("database.get_db_connection", lambda *a, **k: conn)
    monkeypatch.setattr("database.get_coalition_members_table", lambda: None)
    monkeypatch.setattr("app_core.game_ticks.taxes.try_pg_advisory_lock", lambda *a, **k: True)
    monkeypatch.setattr("app_core.game_ticks.taxes.release_pg_advisory_lock", lambda *a, **k: None)
    monkeypatch.setattr("app_core.game_ticks.taxes.should_skip_task", lambda *a, **k: False)

    recorded_batches = []
    def fake_execute_batch(cursor, query, seq, **kwargs):
        recorded_batches.append((query, list(seq)))

    import psycopg2.extras as extras
    monkeypatch.setattr(extras, "execute_batch", fake_execute_batch)

    taxes.tax_income()

    # Verify batch updates were executed
    assert recorded_batches, "Expected batch updates to be executed for re-fetched users"

    cursor_updates = [
        (q, p) for q, p in db.execute_calls
        if "update task_cursors" in str(q).lower()
    ]
    assert cursor_updates, "Expected an UPDATE task_cursors call"
    last_update_sql, last_update_params = cursor_updates[-1]
    assert last_update_params == (0, "tax_income"), f"Expected final cursor to be 0, got {last_update_params}"
