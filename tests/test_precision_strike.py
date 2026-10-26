"""Balance prototype phase 4: narrower roll and precision strikes."""
import random

from attack_scripts import combat_helpers as ch


def test_roll_is_narrow():
    assert (ch.ROLL_LOW, ch.ROLL_HIGH) == (0.8, 1.2)
    r = random.Random(3)
    for _ in range(200):
        assert 80 <= ch.battle_roll(100, r) <= 120


def test_strike_caps_and_zero_cases():
    assert ch.compute_precision_strike("cruisers", 0, "tanks", 100, 0)["killed"] == 0
    assert ch.compute_precision_strike("tanks", 10, "tanks", 100, 0)["killed"] == 0
    r = random.Random(1)
    for _ in range(100):
        res = ch.compute_precision_strike("cruisers", 10**6, "tanks", 1000, 0, rng=r)
        assert res["killed"] <= int(1000 * ch.STRIKE_MAX_FRAC)
        assert res["suppress"] <= ch.SUPPRESS_MAX


def test_cover_and_diminishing_reduce_effect():
    r = random.Random(2)
    base = ch.compute_precision_strike("bombers", 500, "tanks", 10000, 0, rng=r)
    covered = ch.compute_precision_strike("bombers", 500, "tanks", 10000, 10**6, rng=r)
    repeat = ch.compute_precision_strike("bombers", 500, "tanks", 10000, 0, prior_hits=2, rng=r)
    assert base["lost"] == 0 and covered["lost"] > 0
    assert covered["killed"] < base["killed"] * 0.5
    assert repeat["killed"] < base["killed"] * 0.4


def test_small_strike_on_huge_army_is_small():
    res = ch.compute_precision_strike("cruisers", 1, "soldiers", 10**6, 0, rng=random.Random(0))
    assert res["killed"] < 10**6 * 0.001


def test_suppression_penalty():
    units = {"soldiers": 1000, "tanks": 36}  # roughly equal power
    assert ch.suppression_penalty(units, {}) == 0.0
    p = ch.suppression_penalty(units, {"tanks": 0.5})
    assert 0.2 < p < 0.3
    assert ch.suppression_penalty(units, {"tanks": 9, "soldiers": 9}) <= ch.SUPPRESS_MAX
    assert ch.suppression_penalty(units, {"cruisers": 0.5}) == 0.0


def test_precision_ap_costs():
    from wars.action_points import AP_COSTS
    assert AP_COSTS["precision_strike_cruisers"] == ("naval", ch.PRECISION_AP_COST)
    assert AP_COSTS["precision_strike_bombers"] == ("air", ch.PRECISION_AP_COST)


class FakeDB:
    def __init__(self, rows):
        self.rows = rows; self.q = []
    def execute(self, sql, params=None):
        self.q.append(sql); self._last = sql
    def fetchone(self):
        if "to_regclass" in self._last:
            return (self.rows.get("table"),)
        if "SELECT attacker, defender FROM wars" in self._last:
            return self.rows.get("war")
        return None
    def fetchall(self):
        if "FROM precision_strikes" in self._last:
            return [(t,) for t in self.rows.get("recent", [])]
        return []


def test_flow_refuses_without_table_and_over_limit(monkeypatch):
    from wars import precision as P
    ok, msg, _ = P.precision_strike(FakeDB({"table": None}), 1, 5, "cruisers", "tanks")
    assert not ok and "not available" in msg
    monkeypatch.setattr(P, "get_combatant_role", lambda db, w, u: "attacker")
    db = FakeDB({"table": "precision_strikes", "war": (5, 9), "recent": ["tanks"] * ch.STRIKE_DAILY_LIMIT})
    ok, msg, _ = P.precision_strike(db, 1, 5, "cruisers", "tanks")
    assert not ok and "at most" in msg
    ok, msg, _ = P.precision_strike(db, 1, 5, "destroyers", "tanks")
    assert not ok
