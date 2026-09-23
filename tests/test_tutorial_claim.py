"""Tutorial reward claim API."""
from flask import Flask

from app_core.tutorial.routes import claim_tutorial_reward


class FakeCursor:
    def __init__(self, state):
        self.state = state
        self._last = None

    def execute(self, sql, params=None):
        # Emulates the atomic claim statements in app_core/tutorial/routes.py
        # (_claim_chapter/_claim_graduation): the "not already claimed" check
        # and the write are one UPDATE ... RETURNING, so fetchone() is None
        # when the claim was already taken.
        sql_lower = " ".join(sql.lower().split())
        if sql_lower.startswith("select 1 from stats"):
            uid = params[0]
            self._last = (1,) if uid in self.state["stats"] else None
        elif "update stats set tutorial_chapters_claimed" in sql_lower:
            idx, uid, _ = params
            row = self.state["stats"][uid]
            if idx in row["claimed"]:
                self._last = None
            else:
                row["claimed"].append(idx)
                self._last = (list(row["claimed"]),)
        elif "update stats set tutorial_graduated_at" in sql_lower:
            uid = params[0]
            row = self.state["stats"][uid]
            if row["graduated_at"] is not None:
                self._last = None
            else:
                row["graduated_at"] = "now"
                self._last = ("now",)
        elif "update stats set gold = gold + %s" in sql_lower:
            amt, uid = params
            self.state["stats"][uid]["gold"] += amt

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
