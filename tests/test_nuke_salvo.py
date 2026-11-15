"""Nuke rework phase 2: salvo targeting, flat cost, detection, auto-retaliation gating."""
from wars import nuclear_salvo as ns


def test_flat_costs():
    assert ns.salvo_cost(1_000_000, False) == 750_000
    assert ns.salvo_cost(1_000_000, True) == 400_000
    assert ns.salvo_cost(0, False) == 0 and ns.salvo_cost(None, True) == 0


def test_targets_most_populated_first_one_per_province():
    provs = [{"id": 1, "population": 5}, {"id": 2, "population": 50}, {"id": 3, "population": 20}]
    assert [p["id"] for p in ns.pick_targets(provs, 2)] == [2, 3]
    assert [p["id"] for p in ns.pick_targets(provs, 10)] == [2, 3, 1]  # never more than provinces
    assert ns.pick_targets(provs, 0) == []


def test_detection_chance_star_wars():
    assert ns.detection_chance(False) == 0.25 and ns.detection_chance(True) == 0.5


class _DB:
    def __init__(self, auto):
        self.auto, self.sql, self.rows = auto, [], []

    def execute(self, sql, params=()):
        s = " ".join(sql.split())
        self.sql.append(s)
        self.rows = [(self.auto,)] if "FROM user_nuke_settings" in s else []

    def fetchone(self):
        return self.rows[0] if self.rows else None


def test_no_retaliation_when_flag_off_or_not_opted_in(monkeypatch):
    monkeypatch.setattr(ns.nuke_rework, "enabled", lambda *a, **k: False)
    assert ns.maybe_auto_retaliate(_DB(True), 1, 2, 3) is False
    monkeypatch.setattr(ns.nuke_rework, "enabled", lambda *a, **k: True)
    assert ns.maybe_auto_retaliate(_DB(False), 1, 2, 3) is False


def test_undetected_launch_does_not_retaliate(monkeypatch):
    monkeypatch.setattr(ns.nuke_rework, "enabled", lambda *a, **k: True)
    db = _DB(True)
    assert ns.maybe_auto_retaliate(db, 1, 2, 3, rng=lambda: 0.99) is False
    assert any("INSERT INTO news" in s for s in db.sql)


def test_detected_launch_fires_salvo_auto(monkeypatch):
    monkeypatch.setattr(ns.nuke_rework, "enabled", lambda *a, **k: True)
    called = {}

    def fake(db, vid, wid, auto=False):
        called.update(v=vid, w=wid, auto=auto)
        return {"enemy_name": "X", "attacker_name": "Y", "fired": 2, "intercepted": 1}

    monkeypatch.setattr(ns, "execute_salvo", fake)
    monkeypatch.setattr(ns, "_has_star_wars", lambda *a: False)
    assert ns.maybe_auto_retaliate(_DB(True), 1, 2, 3, rng=lambda: 0.1) is True
    assert called == {"v": 1, "w": 3, "auto": True}
