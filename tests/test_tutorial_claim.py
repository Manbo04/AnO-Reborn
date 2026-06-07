"""Tutorial reward claim API."""
from flask import Flask

from app_core.tutorial.routes import claim_tutorial_reward


class FakeCursor:
    def __init__(self, state):
        self.state = state
        self._last = None

    def execute(self, sql, params=None):
        sql_lower = sql.lower()
        if "tutorial_chapters_claimed" in sql_lower and "from stats" in sql_lower:
            uid = params[0]
            row = self.state["stats"].setdefault(
                uid, {"claimed": [], "graduated_at": None, "gold": 0}
            )
            self._last = (row["claimed"], row["graduated_at"])
        elif "update stats set tutorial_chapters_claimed" in sql_lower:
            uid = params[1]
            self.state["stats"][uid]["claimed"] = list(params[0])
        elif "update stats set tutorial_graduated_at" in sql_lower:
            uid = params[0]
            self.state["stats"][uid]["graduated_at"] = "now"
        elif "update stats set gold = gold + %s" in sql_lower:
            amt, uid = params
            self.state["stats"][uid]["gold"] += amt
        elif "alter table stats" in sql_lower:
            pass

    def fetchone(self):
        return self._last


class FakeCursorCM:
    def __init__(self, state):
        self.state = state

    def __enter__(self):
        return FakeCursor(self.state)

    def __exit__(self, exc_type, exc, tb):
        return False


def test_claim_chapter_reward(monkeypatch):
    state = {"stats": {42: {"claimed": [], "graduated_at": None, "gold": 0}}}
    granted_resources = []

    def fake_give_resource(_bank, uid, resource, amount, cursor=None):
        granted_resources.append((uid, resource, amount))
        return True

    monkeypatch.setattr(
        "app_core.tutorial.routes.get_request_cursor",
        lambda: FakeCursorCM(state),
    )
    monkeypatch.setattr("app_core.tutorial.routes.give_resource", fake_give_resource)
    monkeypatch.setattr("database.invalidate_user_cache", lambda _uid: None)

    app = Flask(__name__)
    app.secret_key = "test"
    with app.test_request_context(
        "/api/tutorial/claim",
        method="POST",
        json={"chapter_index": 0},
    ):
        from flask import session

        session["user_id"] = 42
        resp = claim_tutorial_reward()
        data = resp.get_json()

    assert data["ok"] is True
    assert data["granted"]["lumber"] == 10_000
    assert data["granted"]["rations"] == 5_000
    assert 0 in state["stats"][42]["claimed"]


def test_claim_graduation_bonus(monkeypatch):
    state = {"stats": {42: {"claimed": list(range(10)), "graduated_at": None, "gold": 0}}}
    granted_resources = []

    def fake_give_resource(_bank, uid, resource, amount, cursor=None):
        granted_resources.append((uid, resource, amount))
        return True

    monkeypatch.setattr(
        "app_core.tutorial.routes.get_request_cursor",
        lambda: FakeCursorCM(state),
    )
    monkeypatch.setattr("app_core.tutorial.routes.give_resource", fake_give_resource)
    monkeypatch.setattr("database.invalidate_user_cache", lambda _uid: None)

    app = Flask(__name__)
    app.secret_key = "test"
    with app.test_request_context(
        "/api/tutorial/claim",
        method="POST",
        json={"graduate": True},
    ):
        from flask import session

        session["user_id"] = 42
        resp = claim_tutorial_reward()
        data = resp.get_json()

    assert data["ok"] is True
    assert data["granted"]["money"] == 10_000_000
    assert data["granted"]["rations"] == 100_000
    assert state["stats"][42]["graduated_at"] is not None
