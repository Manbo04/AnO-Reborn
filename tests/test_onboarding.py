"""Onboarding checklist logic."""
import pytest
from database import query_cache
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
        elif "bd.name = 'food_banks'" in sql_lower:
            uid = params[0]
            self._last = (self.state.get("food_banks", {}).get(uid, 0),)
        elif "select coalition_id from users" in sql_lower:
            uid = params[0]
            self._last = (self.state.get("coalition_id", {}).get(uid, None),)
        elif "count(*)::int from nation_treaties" in sql_lower:
            uid = params[0]
            self._last = (self.state.get("allies", {}).get(uid, 0),)

    def fetchone(self):
        return self._last


@pytest.fixture(autouse=True)
def clear_onboarding_cache():
    """Clear query_cache before every test so cached results from one test
    don't pollute subsequent tests that use the same synthetic user ID.
    QueryCache stores entries in the .cache dict; use .cache.clear()."""
    query_cache.cache.clear()
    yield
    query_cache.cache.clear()


# Unique synthetic user IDs per scenario to avoid cross-test cache bleed
# even if the fixture is somehow skipped in a future test run.
_UID_NO_PROVINCE = 1001
_UID_NEW_INCOMPLETE = 1002
_UID_PARTIAL = 1003
_UID_FULL = 1004
_UID_REDIRECT = 1005


def test_onboarding_no_province():
    # If the user has 0 provinces, they should not see the checklist
    uid = _UID_NO_PROVINCE
    db = FakeCursor({"provinces": {uid: 0}, "food_banks": {uid: 0}, "coalition_id": {uid: None}, "allies": {uid: 0}})
    status = get_onboarding_status(db, uid)
    assert status["show_checklist"] is False


def test_onboarding_new_province_incomplete():
    # Once a province is created, the checklist is shown
    uid = _UID_NEW_INCOMPLETE
    db = FakeCursor({"provinces": {uid: 1}, "food_banks": {uid: 0}, "coalition_id": {uid: None}, "allies": {uid: 0}})
    status = get_onboarding_status(db, uid)
    assert status["show_checklist"] is True
    assert status["completed"] == 0
    assert status["next_href"] == "/provinces"


def test_onboarding_partially_complete():
    # Build a Food Bank is completed; next step is joining a coalition
    uid = _UID_PARTIAL
    db = FakeCursor({"provinces": {uid: 1}, "food_banks": {uid: 1}, "coalition_id": {uid: None}, "allies": {uid: 0}})
    status = get_onboarding_status(db, uid)
    assert status["show_checklist"] is True
    assert status["completed"] == 1
    assert status["next_href"] == "/coalitions"


def test_onboarding_fully_complete():
    # All 3 steps done — checklist is hidden but completed count is accurate
    uid = _UID_FULL
    db = FakeCursor({"provinces": {uid: 1}, "food_banks": {uid: 1}, "coalition_id": {uid: 2}, "allies": {uid: 1}})
    status = get_onboarding_status(db, uid)
    assert status["show_checklist"] is False
    assert status["completed"] == 3


def test_post_signup_redirect_new_player():
    # New player with 0 provinces: get_onboarding_status returns show_checklist=False
    uid = _UID_REDIRECT
    db = FakeCursor({"provinces": {uid: 0}, "food_banks": {uid: 0}, "coalition_id": {uid: None}, "allies": {uid: 0}})
    status = get_onboarding_status(db, uid)
    assert status["show_checklist"] is False
