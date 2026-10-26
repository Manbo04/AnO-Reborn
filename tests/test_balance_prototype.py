"""Balance prototype (2026-10): value-weighted presence, multiplicative
battle roll, morale floors, casualty caps, entrenchment, nuke tuning."""

import random
from datetime import datetime, timedelta, timezone

import pytest

from attack_scripts import combat_helpers as C
from wars import action_points, nuclear as nk

PRICE = dict(soldiers=250, tanks=7000, artillery=14000, bombers=22000, fighters=30000,
             apaches=28000, destroyers=26000, cruisers=48000, submarines=40000,
             aircraft_carriers=220000)


def test_presence_is_roughly_equal_per_gold():
    budget = 10_000_000
    vals = {u: C.compute_unit_amount_bonus([u], {u: budget // p}) for u, p in PRICE.items()}
    lo, hi = min(vals.values()), max(vals.values())
    assert hi / lo < 1.05


def test_battle_roll_range():
    rng = random.Random(1)
    rolls = [C.battle_roll(100.0, rng) for _ in range(2000)]
    assert min(rolls) >= 100 * C.ROLL_LOW and max(rolls) <= 100 * C.ROLL_HIGH
    assert C.battle_roll(0.0, rng) == 0.0


@pytest.mark.parametrize("wt,floor", [(1.0, 6), (1.24, 6), (1.25, 12), (1.74, 12), (1.75, 20), (5, 20)])
def test_morale_floor_by_win_type(wt, floor):
    assert C.morale_floor(wt, {"soldiers": 10}) == floor


def test_morale_floor_empty_loser_and_cap():
    assert C.morale_floor(1.0, {"soldiers": 0}) == C.MORALE_FLOOR_EMPTY
    huge = {"nukes": 10_000}
    assert C.compute_morale_delta(huge, huge, huge, False, 5) == C.MORALE_DELTA_CAP


def test_loser_casualty_cap():
    _, lp = C.compute_unit_casualties(0.5, 100, ["tanks"], ["tanks"], {"tanks": 1000},
                                      {"tanks": 1000}, rng=random.Random(0))
    assert dict(lp)["tanks"] <= int(1000 * C.LOSER_MAX_LOSS_FRAC * 1.2) + 1


def test_entrenchment_per_level():
    assert action_points.entrenchment_defense_multiplier(3) == pytest.approx(1.075)


def test_nuke_lethality_values():
    assert nk.POP_LETHALITY == 0.35 and nk.INFRA_LETHALITY == 0.45


class _FakeDB:
    def __init__(self, row):
        self.row = row
        self.sql = None

    def execute(self, sql, params=None):
        self.sql, self.params = sql, params

    def fetchone(self):
        return self.row


def test_target_cooldown_until():
    assert nk.target_cooldown_until(_FakeDB((None,)), 5) is None
    last = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    db = _FakeDB((last,))
    assert nk.target_cooldown_until(db, 5) == last + timedelta(days=nk.TARGET_COOLDOWN_DAYS)
    assert "target_id" in db.sql and db.params == (5, nk.TARGET_COOLDOWN_DAYS)


def test_counter_bonus_is_a_minority_of_presence():
    import units as U

    class S(U.Units):
        def __init__(s, d):
            super().__init__(0, dict(d), selected_units_list=list(d))
            s._unusable_units_cache = set()

    arty, soldiers = S({"artillery": 714}), S({"soldiers": 40000})
    aa, da, ab, db, _ = C.compute_engagement_metrics(arty, soldiers)
    assert 0.10 <= ab / aa <= 0.30


def test_ground_triangle_directions():
    import units as U

    assert U.SoldierUnit(10).attack("tanks")[1] > 0
    assert U.TankUnit(10).attack("artillery")[1] > 0
    assert U.ArtilleryUnit(10).attack("soldiers")[1] > 0
    # airburst vs tanks is small next to the main counter
    assert U.ArtilleryUnit(10).attack("tanks")[1] < U.ArtilleryUnit(10).attack("soldiers")[1] / 4
    assert U.TankUnit(10).attack("soldiers")[1] == 0
    assert U.SoldierUnit(10).attack("artillery")[1] == 0


def test_artillery_pierces_entrenchment():
    assert C.artillery_entrenchment_pierce(["soldiers"], {"soldiers": 100}) == 0
    assert C.artillery_entrenchment_pierce(["artillery"], {"artillery": 10}) == pytest.approx(C.ARTILLERY_ENTRENCH_PIERCE)
    _, _, d_full, _ = C.apply_combat_modifiers(100, 0, 100, 0, entrenchment_level=3)
    _, _, d_pierced, _ = C.apply_combat_modifiers(100, 0, 100, 0, entrenchment_level=3, entrenchment_pierce=0.6)
    assert d_full == pytest.approx(107.5) and d_pierced == pytest.approx(103.0)
