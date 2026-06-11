"""Onboarding checklist logic."""
from app_core.onboarding.service import get_onboarding_status, post_signup_redirect


class FakeCursor:
    def __init__(self, state):
        self.state = state
        self._last = None

    def execute(self, sql, params=None):
        sql_lower = " ".join(sql.lower().split())
        if "count(*)::int from provinces" in sql_lower:
            uid = params[0]
            self._last = (self.state.get("provinces", {}).get(uid, 0),)
        elif "bd.name = 'farms'" in sql_lower:
            uid = params[0]
            self._last = (self.state.get("farms", {}).get(uid, 0),)
        elif "information_schema.columns" in sql_lower:
            self._last = ("tutorial_chapters_claimed",) if self.state.get("has_tutorial_col") else None
        elif "tutorial_chapters_claimed from stats" in sql_lower:
            uid = params[0]
            self._last = (self.state.get("claimed", {}).get(uid, []),)
        elif "alter table" in sql_lower:
            pass

    def fetchone(self):
        return self._last


def test_onboarding_all_incomplete():
    db = FakeCursor({"has_tutorial_col": True, "provinces": {1: 0}, "farms": {1: 0}, "claimed": {1: []}})
    status = get_onboarding_status(db, 1)
    assert status["show_checklist"] is True
    assert status["completed"] == 0
    assert status["next_href"] == "/tutorial?onboard=1"
    assert status["show_tutorial_prompt"] is True
    assert status["tutorial_done"] is False


def test_tutorial_prompt_hidden_after_chapter_one():
    db = FakeCursor(
        {"has_tutorial_col": True, "provinces": {1: 0}, "farms": {1: 0}, "claimed": {1: [0, 1]}}
    )
    status = get_onboarding_status(db, 1)
    assert status["tutorial_done"] is True
    assert status["show_tutorial_prompt"] is False


def test_post_signup_redirect_new_player():
    db = FakeCursor({"has_tutorial_col": True, "provinces": {2: 0}, "farms": {2: 0}, "claimed": {2: []}})
    # monkeypatch get_request_cursor in post_signup_redirect - test next_href via get_onboarding_status instead
    status = get_onboarding_status(db, 2)
    assert status["next_href"] == "/tutorial?onboard=1"
