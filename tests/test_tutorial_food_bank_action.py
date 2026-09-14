"""Regression test: buying a Food Bank must advance the tutorial and grant
its chapter reward, same as farms/distribution centers/mines already did.

Bug report (Discord #likes-and-dislikes, msg 1547236197909270548): a player
bought a Food Bank to finish their starting objective, got no reward, and
the tutorial stopped advancing. Root cause: building_purchase.py's
"TUTORIAL ACTION INTERCEPTION" block and ACTION_CHAPTER_MAP in
app_core/tutorial/routes.py never had a case for "food_banks".
"""
import pytest

from app_core.tutorial.routes import advance_tutorial_step_by_action

pytestmark = pytest.mark.no_server


class FakeCursor:
    """Minimal fake matching the SQL shapes advance_tutorial_step_by_action
    (and the money branch of _apply_rewards) issue against `stats`."""

    def __init__(self, state):
        self.state = state
        self._last = None

    def execute(self, sql, params=None):
        sql_lower = " ".join(sql.lower().split())
        if "select tutorial_chapters_claimed from stats" in sql_lower:
            uid = params[0]
            row = self.state["stats"][uid]
            self._last = (row["claimed"],)
        elif "update stats set tutorial_chapters_claimed = %s, tutorial_step = %s" in sql_lower:
            claimed, tutorial_step, uid = params
            self.state["stats"][uid]["claimed"] = list(claimed)
            self.state["stats"][uid]["tutorial_step"] = tutorial_step
        elif "update stats set gold = gold + %s" in sql_lower:
            amount, uid = params
            self.state["stats"][uid]["gold"] += amount

    def fetchone(self):
        return self._last


def test_food_bank_purchase_advances_tutorial_and_grants_reward():
    state = {"stats": {16: {"claimed": [0, 1, 2], "tutorial_step": 3, "gold": 0}}}
    db = FakeCursor(state)

    advance_tutorial_step_by_action(db, 16, "build_food_bank")

    assert state["stats"][16]["claimed"] == [0, 1, 2, 3]
    assert state["stats"][16]["tutorial_step"] == 4
    assert state["stats"][16]["gold"] == 2_000_000  # CHAPTER_REWARDS[3]


def test_food_bank_purchase_does_not_double_grant():
    state = {"stats": {16: {"claimed": [0, 1, 2, 3], "tutorial_step": 4, "gold": 0}}}
    db = FakeCursor(state)

    advance_tutorial_step_by_action(db, 16, "build_food_bank")

    # Already claimed -> no-op, no double reward.
    assert state["stats"][16]["claimed"] == [0, 1, 2, 3]
    assert state["stats"][16]["gold"] == 0
