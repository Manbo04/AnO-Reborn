import tasks
import datetime


class FakeCursor:
    def __init__(self, fetchall_return=None, fetchone_returns=None):
        self._fetchall = fetchall_return or []
        self._fetchone_returns = list(fetchone_returns or [])
        self.execute_calls = []

    def execute(self, query, params=None):
        self.execute_calls.append((query, params))

    def fetchall(self):
        return self._fetchall

    def fetchone(self):
        if self._fetchone_returns:
            return self._fetchone_returns.pop(0)
        return None


class FakeConn:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self, cursor_factory=None):
        return self.db


def test_tax_income_uses_row_lock_and_updates(monkeypatch):
    # Simulate one user in the system
    user_rows = [(42,)]

    # For the SELECT ... FOR UPDATE return None (no last_run) so it proceeds
    db = FakeCursor(fetchall_return=user_rows, fetchone_returns=[None])
    conn = FakeConn(db)
    monkeypatch.setattr("database.get_db_connection", lambda: conn)

    recorded = {"batch_calls": []}

    def fake_execute_batch(db_cursor, query, seq, **kwargs):
        recorded["batch_calls"].append((query, list(seq)))

    import psycopg2.extras as extras

    monkeypatch.setattr(extras, "execute_batch", fake_execute_batch)

    import importlib

    importlib.reload(tasks)

    # make calc_ti produce money so updates happen
    monkeypatch.setattr(tasks, "calc_ti", lambda uid: (100, 0))

    tasks.tax_income()

    # Check that we attempted to insert a task_runs row and used FOR UPDATE
    execute_sqls = [q for q, _ in db.execute_calls]
    assert any(
        "INSERT INTO task_runs (task_name, last_run) VALUES (%s, NULL)" in s
        for s in execute_sqls
    )
    assert any(
        "FOR UPDATE" in s for s in execute_sqls
    ), "expected SELECT ... FOR UPDATE to be used"

    # Ensure updates were invoked
    assert recorded["batch_calls"], "expected batch updates to be performed"


def test_tax_income_skips_if_recent_last_run(monkeypatch):
    # Simulate last_run very recent
    recent = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        seconds=10
    )

    # Simulate advisory lock acquisition success, then a recent last_run row
    db = FakeCursor(fetchall_return=[(42,)], fetchone_returns=[(True,), (recent,)])
    conn = FakeConn(db)
    monkeypatch.setattr("database.get_db_connection", lambda: conn)

    recorded = {"batch_calls": []}

    def fake_execute_batch(db_cursor, query, seq, **kwargs):
        recorded["batch_calls"].append((query, list(seq)))

    import psycopg2.extras as extras

    monkeypatch.setattr(extras, "execute_batch", fake_execute_batch)

    import importlib

    importlib.reload(tasks)

    # Patch calc_ti but it should not be called
    monkeypatch.setattr(tasks, "calc_ti", lambda uid: (100, 0))

    tasks.tax_income()

    # No batch updates should have happened because we skipped
    assert not recorded["batch_calls"], "expected no updates when last_run is recent"
    # Also verify the SELECT FOR UPDATE was present
    execute_sqls = [q for q, _ in db.execute_calls]
    assert any(
        "FOR UPDATE" in s for s in execute_sqls
    ), "expected SELECT ... FOR UPDATE to be used on skip"
