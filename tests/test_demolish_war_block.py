"""Selling a building through demolish_structure is blocked during an active war,
matching the other sell routes. No database needed."""
import pytest

pytestmark = pytest.mark.no_server


def _fake_conn(at_war):
    class Cur:
        def __init__(self):
            self.last = ""

        def execute(self, sql, params=()):
            self.last = sql

        def fetchone(self):
            if "FROM wars" in self.last:
                return (1,) if at_war else None
            return None  # building lookup: not found, ends the call early

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def cursor(self):
            return Cur()

        def commit(self):
            pass

    return Conn()


def test_blocked_while_at_war(monkeypatch):
    import action_loop

    monkeypatch.setattr("action_loop.get_db_connection", lambda: _fake_conn(True))
    with pytest.raises(action_loop.ActionLoopError, match="at war"):
        action_loop.demolish_structure(user_id=1, building_id=5, quantity=1, province_id=1)


def test_war_check_runs_before_the_building_lookup(monkeypatch):
    import action_loop

    monkeypatch.setattr("action_loop.get_db_connection", lambda: _fake_conn(True))
    # If the lookup ran first this would raise "Building not found" instead.
    with pytest.raises(action_loop.ActionLoopError) as exc:
        action_loop.demolish_structure(user_id=1, building_id=5, quantity=1, province_id=1)
    assert "Building not found" not in str(exc.value)


def test_allowed_when_not_at_war(monkeypatch):
    import action_loop

    monkeypatch.setattr("action_loop.get_db_connection", lambda: _fake_conn(False))
    with pytest.raises(action_loop.ActionLoopError, match="Building not found"):
        action_loop.demolish_structure(user_id=1, building_id=5, quantity=1, province_id=1)
