"""Command Briefing tour (app_core/tutorial/tour.py): state derived from real game data."""
import pytest

import app_core.tutorial.routes as troutes
from app_core.tutorial import tour
from app_core.tutorial.tour import STEPS, compute_tour


class _Cur:
    """Fake cursor answering the exact queries compute_tour() makes."""

    def __init__(self, claimed=None, graduated=None, buildings=None, soldiers=0, capital=11):
        self.claimed = list(claimed or [])
        self.graduated = graduated
        self.buildings = buildings or {}
        self.soldiers = soldiers
        self.capital = capital
        self._rows = None

    def execute(self, q, params=None):
        q = " ".join(q.split())
        if q.startswith("SELECT tutorial_chapters_claimed"):
            self._rows = [(self.claimed, self.graduated)]
        elif "FROM user_buildings" in q:
            self._rows = list(self.buildings.items())
        elif "FROM user_military" in q:
            self._rows = [(self.soldiers,)]
        elif q.startswith("SELECT id FROM provinces"):
            self._rows = [(self.capital,)] if self.capital else []
        else:
            self._rows = []

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows or []


@pytest.fixture(autouse=True)
def _fake_claims(monkeypatch):
    """Replace the DB-writing claim helpers with in-memory versions on the cursor."""
    def claim(db, uid, idx):
        if idx in db.claimed:
            return None
        db.claimed.append(idx)
        return {"money": 1}

    def grad(db, uid):
        if db.graduated:
            return False
        db.graduated = True
        return True

    monkeypatch.setattr(troutes, "_claim_chapter", claim)
    monkeypatch.setattr(troutes, "_claim_graduation", grad)
    monkeypatch.setattr(troutes, "_apply_rewards", lambda db, uid, r: dict(r))


def test_fresh_nation_starts_at_first_step():
    s = compute_tour(_Cur(), 1)
    assert s["ok"] and s["current"] == 0 and s["completed"] == 0
    assert s["steps"][1]["href"] == "/province/11"
    assert not s["newly_completed"]


def test_visit_only_counts_for_visit_steps():
    db = _Cur()
    s = compute_tour(db, 1, visited="survey")
    assert [n["key"] for n in s["newly_completed"]] == ["survey"]
    s = compute_tour(db, 1, visited="power")  # state step: a "visit" can't complete it
    assert not s["steps"][tour.STEP_INDEX["power"]]["done"]


def test_state_steps_follow_real_buildings_and_units():
    db = _Cur(buildings={"wind_farms": 1, "farms": 2, "copper_mines": 1}, soldiers=5)
    s = compute_tour(db, 1)
    done = {n["key"] for n in s["newly_completed"]}
    assert done == {"power", "farms", "extract", "army"}
    assert s["current"] == 0  # visits still outstanding, stores not built


def test_rewards_paid_once_and_graduation():
    db = _Cur(claimed=[i for i, st in enumerate(STEPS) if st["key"] != "allies"])
    s = compute_tour(db, 1, visited="allies")
    assert s["graduated"] and s["graduation_reward"]
    again = compute_tour(db, 1, visited="allies")
    assert not again["newly_completed"] and again["graduation_reward"] is None


def test_no_capital_falls_back_to_provinces_list():
    s = compute_tour(_Cur(capital=None), 1)
    assert s["steps"][1]["href"] == "/provinces"
