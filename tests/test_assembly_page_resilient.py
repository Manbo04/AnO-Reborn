"""The Assembly page must still render if an assembly_* query fails."""
from contextlib import contextmanager

import pytest

import app as app_module


class _FakeCursor:
    """Fails on assembly_* queries, answers the poll queries."""

    def __init__(self):
        self._rows = []
        self.rolled_back_to_savepoint = False

    def execute(self, sql, params=None):
        text = " ".join(str(sql).split())
        if text.startswith("ROLLBACK TO SAVEPOINT"):
            self.rolled_back_to_savepoint = True
            return
        if "FROM assembly_" in text:
            raise RuntimeError('relation "assembly_effects" does not exist')
        if "GROUP BY vote_option" in text:
            self._rows = [{"vote_option": "Terra", "vote_count": 2}]
        elif "SELECT vote_option FROM poll_votes" in text:
            self._rows = [{"vote_option": "Terra"}]
        else:
            self._rows = []

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


def test_assembly_page_survives_failing_assembly_queries(monkeypatch):
    import app_core.game_engine.routes as routes

    cur = _FakeCursor()

    @contextmanager
    def fake_cursor(*args, **kwargs):
        yield cur

    monkeypatch.setattr(routes, "get_request_cursor", fake_cursor)
    app = app_module.app
    app.config["WTF_CSRF_ENABLED"] = False
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = 1
    resp = client.get("/assembly")
    assert resp.status_code == 200
    assert cur.rolled_back_to_savepoint
