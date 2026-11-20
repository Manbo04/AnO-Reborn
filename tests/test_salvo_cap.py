"""Civilian damage cap per Fire All salvo (flag nuke_salvo_civilian_cap).

Pure math first (no database), then the salvo loop with fakes, then one DB flow that
fires a real salvo through execute_salvo with the flag off and on.
"""

import os
import random

import pytest

from wars import nuclear as nk
from wars import nuclear_salvo as ns
from wars import salvo_cap as sc

pure = pytest.mark.no_server


# ----------------------------------------------------------------- constants / flag
@pure
def test_default_caps_are_25_percent():
    assert sc.SALVO_CIVILIAN_CAP_DEATHS == 0.25
    assert sc.SALVO_CIVILIAN_CAP_BUILDINGS == 0.25
    assert sc.SALVO_CIVILIAN_CAP_CITIES == 0.25
    # nuclear_salvo re-exports the two numbers Dede agreed, next to SALVO_FIRST_COST
    assert (
        ns.SALVO_CIVILIAN_CAP_DEATHS == 0.25 and ns.SALVO_CIVILIAN_CAP_BUILDINGS == 0.25
    )


@pure
def test_flag_key_and_fail_safe(monkeypatch):
    seen = {}

    def fake(key, user_id=None, default=False):
        seen["key"] = key
        return True

    monkeypatch.setattr(sc, "is_on", fake)
    assert sc.enabled(1) is True and seen["key"] == "nuke_salvo_civilian_cap"

    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(sc, "is_on", boom)
    assert sc.enabled(1) is False  # an unreadable flag means the old behaviour


# ------------------------------------------------------------------- SalvoCap math
@pure
def test_first_warhead_is_never_limited_and_lifts_the_cap():
    cap = sc.SalvoCap(pop_total=1000, buildings_total=1000, cities_total=100)
    assert cap.cap == {"deaths": 250, "buildings": 250, "cities": 25}
    assert cap.remaining() == {"deaths": None, "buildings": None, "cities": None}
    assert not cap.exhausted()
    # a first warhead that kills 310 (above 25%) is applied in full ...
    cap.record(deaths=310, buildings=100, cities=5)
    assert cap.cap["deaths"] == 310  # ... and becomes the cap
    assert cap.cap["buildings"] == 250  # its building damage was under 25%
    # nothing more may die, but 150 more buildings may be destroyed
    assert cap.remaining() == {"deaths": 0, "buildings": 150, "cities": 20}
    assert not cap.exhausted()


@pure
def test_exhausted_only_when_every_measure_is_full():
    cap = sc.SalvoCap(100, 100, 10)
    cap.record(30, 30, 3)
    assert cap.exhausted()  # all three first-warhead numbers are above 25%
    cap = sc.SalvoCap(100, 100, 10)
    cap.record(30, 10, 1)
    assert not cap.exhausted()  # buildings and cities still have room


@pure
def test_empty_nation_has_zero_cap_but_still_takes_the_first_warhead():
    cap = sc.SalvoCap(0, 0, 0)
    assert cap.cap == {"deaths": 0, "buildings": 0, "cities": 0}
    assert cap.remaining()["deaths"] is None  # first warhead unlimited
    cap.record(0, 0, 0)
    assert cap.exhausted()


@pure
def test_clamp():
    assert sc.clamp(500, None) == 500  # no limit yet
    assert sc.clamp(500, 120) == 120
    assert sc.clamp(50, 120) == 50
    assert sc.clamp(500, 0) == 0
    assert sc.clamp(-5, 10) == 0


@pure
def test_one_warhead_salvo_is_identical_to_today():
    """A single warhead gets through at full strength however big it is."""
    cap = sc.SalvoCap(pop_total=3_000_000, buildings_total=300, cities_total=30)
    rem = cap.remaining()
    assert sc.clamp(930_000, rem["deaths"]) == 930_000  # 31% of the nation
    assert sc.clamp(105, rem["buildings"]) == 105  # 35% of its buildings


def _run_salvo(provinces, cap):
    """Pure model of a salvo: blast, then 0.5% fallout on every province, per warhead."""
    pops = [p["pop"] for p in provinces]
    blds = [p["buildings"] for p in provinces]
    cities = [p["cities"] for p in provinces]
    fired = 0
    for i, p in enumerate(provinces):
        if cap and cap.exhausted():
            continue
        dmg = nk.strike_damage(
            {
                "population": pops[i],
                "land": p["land"],
                "citycount": cities[i],
                "happiness": 0,
            },
            1.0,
        )
        rem = (
            cap.remaining()
            if cap
            else {"deaths": None, "buildings": None, "cities": None}
        )
        blast = sc.clamp(dmg["deaths"], rem["deaths"])
        city_loss = sc.clamp(dmg["cities_destroyed"], rem["cities"])
        (bl,) = [
            sc.allocate_building_losses([blds[i]], dmg["infra_frac"], rem["buildings"])[
                0
            ]
        ]
        pops[i] -= blast
        allowed = None if rem["deaths"] is None else max(0, rem["deaths"] - blast)
        pct = sc.fallout_pct_for_allowance(pops, 0.005, allowed)
        fall = sc.fallout_deaths(pops, pct)
        pops = [x - sc.fallout_deaths([x], pct) for x in pops]
        blds[i] -= bl
        cities[i] -= city_loss
        if cap:
            cap.record(blast + fall, bl, city_loss)
        fired += 1
    return {
        "fired": fired,
        "deaths": sum(p["pop"] for p in provinces) - sum(pops),
        "buildings": sum(p["buildings"] for p in provinces) - sum(blds),
    }


@pure
@pytest.mark.parametrize("n_prov", [1, 5, 20, 90])
def test_salvo_never_passes_max_of_cap_and_first_warhead(n_prov):
    prov = {"pop": 30_000_000, "land": 3870, "cities": 310, "buildings": 4180}
    provinces = [dict(prov) for _ in range(n_prov)]
    pop_total = sum(p["pop"] for p in provinces)
    bld_total = sum(p["buildings"] for p in provinces)
    cap = sc.SalvoCap(pop_total, bld_total, sum(p["cities"] for p in provinces))
    out = _run_salvo(provinces, cap)
    first = _run_salvo(provinces[:1], None)  # what the first warhead alone does
    assert out["deaths"] <= max(int(pop_total * 0.25), first["deaths"] + 1)
    assert out["buildings"] <= max(int(bld_total * 0.25), first["buildings"])


@pure
def test_random_nations_never_exceed_the_cap():
    rng = random.Random(7)
    for _ in range(60):
        n = rng.randint(1, 40)
        provinces = [
            {
                "pop": rng.randint(10_000, 80_000_000),
                "land": rng.randint(1, 2000),
                "cities": rng.randint(1, 300),
                "buildings": rng.randint(0, 3000),
            }
            for _ in range(n)
        ]
        provinces.sort(
            key=lambda p: -p["pop"]
        )  # Fire All hits the most populated first
        pop_total = sum(p["pop"] for p in provinces)
        bld_total = sum(p["buildings"] for p in provinces)
        cap = sc.SalvoCap(pop_total, bld_total, sum(p["cities"] for p in provinces))
        out = _run_salvo(provinces, cap)
        first = _run_salvo(provinces[:1], None)
        assert out["deaths"] <= max(
            int(pop_total * 0.25), first["deaths"] + 1
        ), provinces
        assert out["buildings"] <= max(
            int(bld_total * 0.25), first["buildings"]
        ), provinces
        # the first warhead is exactly what it would be without any cap
        solo = _run_salvo(provinces[:1], sc.SalvoCap(pop_total, bld_total, 1))
        assert solo == first


# --------------------------------------------------------------------------- fallout
@pure
def test_fallout_deaths_matches_floor_per_province():
    pops = [1000, 199, 0, 10_000_000]
    assert sc.fallout_deaths(pops, 0.005) == 5 + 0 + 0 + 50_000
    assert sc.fallout_deaths([], 0.005) == 0


@pure
def test_fallout_pct_is_unchanged_when_it_fits():
    pops = [1_000_000, 2_000_000]
    assert sc.fallout_pct_for_allowance(pops, 0.005, 15_000) == 0.005  # exactly fits
    assert sc.fallout_pct_for_allowance(pops, 0.005, None) == 0.005


@pure
def test_fallout_pct_is_the_largest_that_fits():
    pops = [1_000_000, 2_000_000, 500_000]
    for allowed in (0, 1, 777, 5_000, 17_499):
        pct = sc.fallout_pct_for_allowance(pops, 0.005, allowed)
        assert sc.fallout_deaths(pops, pct) <= allowed
        assert pct <= 0.005
        # not wasteful: a hair more would pass the allowance
        assert allowed == 0 or sc.fallout_deaths(pops, pct + 1e-6) > allowed


# ---------------------------------------------------------------- building losses
@pure
def test_building_losses_unlimited_is_floor_per_type():
    assert sc.allocate_building_losses([100, 33, 5, 0], 0.5, None) == [50, 16, 2, 0]
    assert sc.allocate_building_losses([100, 33], 0.5, 10_000) == [50, 16]


@pure
def test_building_losses_are_trimmed_to_the_allowance():
    out = sc.allocate_building_losses([100, 33, 5], 0.5, 30)
    assert sum(out) == 30 and all(o <= w for o, w in zip(out, [50, 16, 2]))
    assert sc.allocate_building_losses([100, 33, 5], 0.5, 0) == [0, 0, 0]
    rng = random.Random(3)
    for _ in range(200):
        q = [rng.randint(0, 500) for _ in range(rng.randint(1, 12))]
        frac = rng.random()
        allowed = rng.randint(0, 400)
        wanted = sc.allocate_building_losses(q, frac, None)
        got = sc.allocate_building_losses(q, frac, allowed)
        assert sum(got) <= allowed
        assert all(0 <= g <= w for g, w in zip(got, wanted))
        assert sum(got) == min(allowed, sum(wanted))


# -------------------------------------------------------- the salvo loop (fakes only)
class _Db:
    def __init__(self):
        self.sql = []

    def execute(self, sql, params=()):
        self.sql.append(" ".join(sql.split()))

    def fetchone(self):
        return None


def _plan(n_provs, nukes):
    return {
        "blocked": None,
        "provinces": [{"id": i, "population": 100 - i} for i in range(n_provs)],
        "nukes": nukes,
        "influence": 1_000_000,
        "is_retaliation": False,
        "enemy_id": 9,
        "enemy_name": "E",
        "attacker_name": "A",
    }


def _patch_loop(monkeypatch, n_provs, nukes, cap_on, per_warhead):
    calls = []
    monkeypatch.setattr(ns.nuke_rework, "enabled", lambda *a, **k: True)
    monkeypatch.setattr(ns, "plan_strike", lambda *a, **k: _plan(n_provs, nukes))
    monkeypatch.setattr(ns.salvo_cap, "enabled", lambda *a, **k: cap_on)
    monkeypatch.setattr(
        ns, "read_salvo_cap", lambda db, eid: sc.SalvoCap(1000, 1000, 100)
    )
    monkeypatch.setattr(ns, "maybe_auto_retaliate", lambda *a, **k: False)

    def fake_strike(db, a, w, pid, salvo=False, cost_override=None, salvo_cap=None):
        calls.append({"province": pid, "cap": salvo_cap, "cost": cost_override})
        if salvo_cap is None:
            return {
                "deaths": per_warhead,
                "buildings_destroyed": 0,
                "cities_destroyed": 0,
            }
        rem = salvo_cap.remaining()
        d = sc.clamp(per_warhead, rem["deaths"])
        if per_warhead and d == 0:  # this fake only models deaths
            raise ns.SalvoClamped("cap")
        salvo_cap.record(d, 0, 0)
        return {"deaths": d, "buildings_destroyed": 0, "cities_destroyed": 0}

    monkeypatch.setattr(ns, "execute_strike", fake_strike)
    return calls


@pure
def test_flag_off_the_salvo_loop_is_unchanged(monkeypatch):
    calls = _patch_loop(monkeypatch, n_provs=6, nukes=6, cap_on=False, per_warhead=200)
    out = ns.execute_salvo(_Db(), 1, 5)
    assert [c["cap"] for c in calls] == [
        None
    ] * 6  # no cap object reaches execute_strike
    assert (
        out["fired"] == 6 and out["deaths"] == 1200
    )  # 120% of the 1000 people: no cap
    assert out["capped"] is False and out["clamped"] == 0 and out["spared_nukes"] == 0


@pure
def test_flag_on_clamped_warheads_stay_in_stock(monkeypatch):
    # each warhead kills 200 of 1000 (20%). cap 250 (first warhead 200 is under it).
    # warhead 1: 200, warhead 2: 50 (clamped), warhead 3+: nothing left, not fired.
    calls = _patch_loop(monkeypatch, n_provs=6, nukes=6, cap_on=True, per_warhead=200)
    out = ns.execute_salvo(_Db(), 1, 5)
    assert out["deaths"] == 250
    assert out["fired"] == 2 and out["clamped"] == 4 and out["spared_nukes"] == 4
    assert out["capped"] is True
    assert len(calls) <= 6


@pure
def test_flag_on_single_warhead_is_unchanged(monkeypatch):
    calls = _patch_loop(monkeypatch, n_provs=1, nukes=1, cap_on=True, per_warhead=700)
    out = ns.execute_salvo(_Db(), 1, 5)
    assert (
        out["fired"] == 1 and out["deaths"] == 700
    )  # 70% of the nation, not cut to 25%
    assert out["capped"] is False and out["spared_nukes"] == 0
    assert calls[0]["cap"] is not None


@pure
def test_intercepted_warheads_count_for_nothing(monkeypatch):
    monkeypatch.setattr(ns.nuke_rework, "enabled", lambda *a, **k: True)
    monkeypatch.setattr(ns, "plan_strike", lambda *a, **k: _plan(3, 3))
    monkeypatch.setattr(ns.salvo_cap, "enabled", lambda *a, **k: True)
    cap = sc.SalvoCap(1000, 1000, 100)
    monkeypatch.setattr(ns, "read_salvo_cap", lambda db, eid: cap)
    monkeypatch.setattr(ns, "maybe_auto_retaliate", lambda *a, **k: False)
    seq = iter([True, True, False])

    def fake_strike(db, a, w, pid, salvo=False, cost_override=None, salvo_cap=None):
        if next(seq):  # intercepted: the real execute_strike returns before recording
            return {"intercepted": True, "deaths": 0}
        salvo_cap.record(900, 0, 0)
        return {"deaths": 900}

    monkeypatch.setattr(ns, "execute_strike", fake_strike)
    out = ns.execute_salvo(_Db(), 1, 5)
    assert out["intercepted"] == 2 and out["fired"] == 3
    # the first warhead that got through was the third and is applied in full
    assert cap.used["deaths"] == 900 and cap.landed == 1
    assert out["cost"] > 0  # influence is charged once a warhead got through


@pure
def test_a_clamped_warhead_is_rolled_back_with_its_savepoint(monkeypatch):
    _patch_loop(monkeypatch, n_provs=2, nukes=2, cap_on=True, per_warhead=0)
    # deaths are full, but buildings and cities still have room, so the shortcut
    # exhausted() does not skip it and only the check inside execute_strike can refuse it
    cap = sc.SalvoCap(1000, 1000, 100)
    cap.record(300, 0, 0)
    assert not cap.exhausted()
    monkeypatch.setattr(ns, "read_salvo_cap", lambda d, e: cap)

    def strike(db_, a, w, pid, salvo=False, cost_override=None, salvo_cap=None):
        raise ns.SalvoClamped("cap")

    monkeypatch.setattr(ns, "execute_strike", strike)
    db = _Db()
    out = ns.execute_salvo(db, 1, 5)
    assert out["fired"] == 0 and out["clamped"] == 2 and out["spared_nukes"] == 2
    assert out["cost"] == 0  # nothing got through, so no influence is charged
    rollbacks = [s for s in db.sql if s == "ROLLBACK TO SAVEPOINT nuke_salvo_warhead"]
    assert len(rollbacks) == 2


# ------------------------------------------------------------------ DB flow (local)
needs_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL") or bool(os.getenv("DATABASE_PUBLIC_URL")),
    reason="Needs a LOCAL Postgres in DATABASE_URL (and no DATABASE_PUBLIC_URL)",
)


def _mk_target(db, tag, n_prov, pop_each, farms_each):
    from tests.test_nuclear_strike import _mk_user

    uid, name, first = _mk_user(db, tag, pop_each)
    provs = [first]
    for i in range(1, n_prov):
        db.execute(
            "INSERT INTO provinces (userid, provincename, citycount, land, population, "
            "happiness, pop_working) VALUES (%s, %s, 20, 50, %s, 80, %s) RETURNING id",
            (uid, f"{tag}-{i}", pop_each, pop_each // 2),
        )
        provs.append(db.fetchone()[0])
    for pid in provs:
        db.execute(
            "INSERT INTO user_buildings (user_id, building_id, province_id, quantity) "
            "SELECT %s, building_id, %s, %s FROM building_dictionary WHERE name = 'farms'",
            (uid, pid, farms_each),
        )
        db.execute(
            "INSERT INTO user_buildings (user_id, building_id, province_id, quantity) "
            "SELECT %s, building_id, %s, %s FROM building_dictionary WHERE name = 'coal_mines'",
            (uid, pid, farms_each // 2),
        )
    return uid, provs


def _totals(db, uid):
    db.execute(
        "SELECT COALESCE(SUM(population),0), COALESCE(SUM(citycount),0) FROM provinces WHERE userid=%s",
        (uid,),
    )
    pop, cities = db.fetchone()
    db.execute(
        "SELECT COALESCE(SUM(quantity),0) FROM user_buildings WHERE user_id=%s", (uid,)
    )
    return int(pop), int(db.fetchone()[0]), int(cities)


def _nukes_left(db, uid):
    db.execute(
        "SELECT COALESCE(SUM(um.quantity),0) FROM user_military um JOIN unit_dictionary ud "
        "ON ud.unit_id = um.unit_id WHERE um.user_id=%s AND ud.name='nukes'",
        (uid,),
    )
    return int(db.fetchone()[0])


def _cleanup(ids):
    from database import get_db_connection, query_cache
    from tests._db_cleanup import purge_users_where

    query_cache.invalidate(pattern="influence_")
    with get_db_connection() as conn:
        db = conn.cursor()
        for uid in ids:
            db.execute(
                "DELETE FROM nuclear_strikes WHERE attacker_id=%s OR target_id=%s",
                (uid, uid),
            )
            db.execute("DELETE FROM wars WHERE attacker=%s OR defender=%s", (uid, uid))
            db.execute("DELETE FROM news WHERE destination_id=%s", (uid,))
            db.execute("DELETE FROM user_buildings WHERE user_id=%s", (uid,))
            db.execute("DELETE FROM user_military WHERE user_id=%s", (uid,))
            db.execute("DELETE FROM provinces WHERE userid=%s", (uid,))
            db.execute(
                "DELETE FROM referral_active_days WHERE referred_user_id=%s", (uid,)
            )
            db.execute("DELETE FROM stats WHERE id=%s", (uid,))
            purge_users_where(db, "id=%s", (uid,))
        try:
            db.execute("DELETE FROM world_events WHERE actor_id = ANY(%s)", (ids,))
        except Exception:
            conn.rollback()
        conn.commit()


def _fire(cap_on, n_prov, nukes, monkeypatch):
    """Build a target + attacker, fire a salvo with the flag on/off, return the numbers."""
    from database import get_db_connection, query_cache
    from tests.test_nuclear_strike import _give_nukes, _mk_user

    monkeypatch.setattr("app_core.nuke_rework.enabled", lambda *a, **k: True)
    monkeypatch.setattr(sc, "enabled", lambda *a, **k: cap_on)
    ids = []
    try:
        with get_db_connection() as conn:
            db = conn.cursor()
            a, _, _ = _mk_user(db, "sa", 300_000_000)
            b, b_provs = _mk_target(db, "sb", n_prov, 10_000_000, 100)
            ids = [a, b]
            _give_nukes(db, a, nukes)
            db.execute(
                "INSERT INTO wars (attacker, defender, war_type, agressor_message, start_date, last_visited) "
                "VALUES (%s, %s, 'Raze', 'test', extract(epoch from now()), extract(epoch from now())) RETURNING id",
                (a, b),
            )
            war_id = db.fetchone()[0]
            conn.commit()
        query_cache.invalidate(pattern="influence_")
        with get_db_connection() as conn:
            db = conn.cursor()
            before = _totals(db, b)
            out = ns.execute_salvo(db, a, war_id)
            conn.commit()
            after = _totals(db, b)
            left = _nukes_left(db, a)
            db.execute(
                "SELECT count(*) FROM nuclear_strikes WHERE attacker_id=%s", (a,)
            )
            rows = db.fetchone()[0]
        return before, after, left, rows, out
    finally:
        _cleanup(ids)


@needs_db
def test_db_flag_off_salvo_is_unchanged_and_exceeds_25_percent(monkeypatch):
    before, after, left, rows, out = _fire(
        False, n_prov=4, nukes=4, monkeypatch=monkeypatch
    )
    assert out["fired"] == 4 and left == 0 and rows == 4
    assert out["capped"] is False and out["clamped"] == 0
    assert (before[0] - after[0]) / before[0] > 0.25  # the problem the cap solves
    assert (before[1] - after[1]) / before[1] > 0.25


@needs_db
def test_db_flag_on_salvo_stays_under_the_cap_and_keeps_clamped_nukes(monkeypatch):
    before, after, left, rows, out = _fire(
        True, n_prov=4, nukes=4, monkeypatch=monkeypatch
    )
    first_deaths = out["results"][0]["deaths"] + out["results"][0]["fallout_deaths"]
    first_blds = out["results"][0]["buildings_destroyed"]
    died, lost = before[0] - after[0], before[1] - after[1]
    assert died <= max(int(before[0] * 0.25), first_deaths)
    assert lost <= max(int(before[1] * 0.25), first_blds)
    assert died == pytest.approx(before[0] * 0.25, abs=1)  # the cap is actually reached
    assert out["capped"] is True
    # warheads that were cut to nothing stay in stock and write no strike row
    assert out["fired"] == rows == len(out["results"])
    assert left == 4 - out["fired"] and out["spared_nukes"] == left
    assert (
        out["deaths"] + sum(r.get("fallout_deaths", 0) for r in out["results"]) == died
    )


@needs_db
def test_db_flag_on_single_warhead_matches_flag_off(monkeypatch):
    off = _fire(False, n_prov=1, nukes=1, monkeypatch=monkeypatch)
    on = _fire(True, n_prov=1, nukes=1, monkeypatch=monkeypatch)
    assert off[0] == on[0]  # same starting nation
    assert off[1] == on[1]  # one warhead does exactly what it does today
    assert on[4]["fired"] == 1 and on[4]["capped"] is False
    # one warhead on a one-province nation is above 25%, so a plain cap would have bitten
    assert (on[0][0] - on[1][0]) / on[0][0] > 0.25
