"""Limits on how many buildings one drone / cruise missile strike destroys
(flag strike_building_cap): share cap, lower share for silos, 72h window, and a cap on
the gold value destroyed per gold of units committed.

Pure functions first, then the real /drone_strike and /cruise_missile_strike routes
against the local database, flag off and on.
"""

import os
import random

import pytest

import variables
from wars import strike_building_cap as cap

pytestmark = pytest.mark.no_server

L = cap.StrikeLimits  # (share, recent_lost, max_by_value)


# ---------------------------------------------------------------------------- pure
def test_flag_key_and_fail_safe(monkeypatch):
    seen = {}

    def fake(key, user_id=None, default=False):
        seen["key"] = key
        return True

    monkeypatch.setattr(cap, "is_on", fake)
    assert cap.enabled(1) is True and seen["key"] == "strike_building_cap"

    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(cap, "is_on", boom)
    assert cap.enabled(1) is False


def test_default_constants():
    assert cap.STRIKE_BUILDING_MAX_SHARE == 0.25
    assert cap.STRIKE_SILO_MAX_SHARE == 0.10
    assert cap.STRIKE_BUILDING_MIN_PER_STRIKE == 1
    assert cap.STRIKE_WINDOW_HOURS == 72
    assert cap.STRIKE_VALUE_CAP_MULTIPLE == 20


def test_silos_get_a_lower_share():
    assert cap.share_for("silos") == 0.10
    assert cap.share_for("farms") == cap.share_for("steel_mills") == 0.25


@pytest.mark.parametrize(
    "total,allowed",
    [(0, 0), (1, 1), (3, 1), (4, 1), (7, 1), (8, 2), (400, 100), (401, 100)],
)
def test_max_by_share_first_strike(total, allowed):
    assert cap.max_by_share(total, 0.25) == allowed


def test_max_by_share_window_counts_recent_losses():
    # 1000 farms, 250 already destroyed in the window (750 left): the window total is
    # capped at 25% of the 1000 the target had, so nothing more may fall
    assert cap.max_by_share(750, 0.25, 250) == 0
    # 100 lost earlier: 25% of 1000 is 250, 150 may still fall
    assert cap.max_by_share(900, 0.25, 100) == 150
    # the minimum of one only applies to the first strike in the window
    assert cap.max_by_share(3, 0.25, 1) == 0
    assert cap.max_by_share(3, 0.25, 0) == 1


def test_three_strikes_in_a_row_stop_at_the_share():
    """Round 1 (per-strike cap only) allowed 1 - 0.75^3 = 57.8% in a burst."""
    total = 1000
    lost = 0
    for _ in range(3):
        got = cap.capped_destroyed(total - lost, 5000 // 6, L(0.25, lost, None))
        lost += got
    assert lost == 250  # exactly 25% of the stock, not 57.8%
    # and the old per-strike-only rule, for comparison
    owned, gone = total, 0
    for _ in range(3):
        step = min(owned, max(1, int(owned * 0.25)))
        owned -= step
        gone += step
    assert gone / total == pytest.approx(1 - 0.75**3, abs=0.01)


def test_max_by_value():
    # 1,000 drones = 3,500,000 gold x 20 = 70,000,000: 46 farms of 1,500,000
    assert cap.max_by_value(3_500_000, 1_500_000) == 46
    assert cap.max_by_value(3_500_000, 1_500_000, multiple=100) == 233
    assert cap.max_by_value(3_500_000, 350_000_000) == 0  # silos: out of reach
    assert cap.max_by_value(0, 1_500_000) is None  # unknown price: not applied
    assert cap.max_by_value(3_500_000, 0) is None


def test_capped_destroyed_flag_off_is_the_old_rule():
    assert cap.capped_destroyed(400, 233, None) == 233
    assert cap.capped_destroyed(100, 233, None) == 100  # never more than owned
    assert cap.capped_destroyed(0, 5, None) == 0
    assert cap.capped_destroyed(10, 0, None) == 0


def test_capped_destroyed_takes_the_smallest_cap():
    assert cap.capped_destroyed(400, 233, L(0.25, 0, None)) == 100  # share
    assert cap.capped_destroyed(400, 233, L(0.25, 0, 46)) == 46  # value
    assert cap.capped_destroyed(400, 233, L(0.25, 90, None)) == 32  # window: 122 - 90
    assert (
        cap.capped_destroyed(400, 50, L(0.25, 0, 500)) == 50
    )  # small strike untouched
    assert cap.capped_destroyed(3, 500, L(0.25, 0, None)) == 1  # minimum of one
    assert cap.capped_destroyed(400, 0, L(0.25, 0, 46)) == 0
    # the value cap is NOT overridden by the minimum of one (a drone cannot level a silo)
    assert cap.capped_destroyed(40, 93, L(0.10, 0, 0)) == 0


def test_never_above_any_cap_for_any_input():
    rng = random.Random(5)
    for _ in range(1000):
        total = rng.randint(0, 10_000)
        wanted = rng.randint(0, 50_000)
        recent = rng.randint(0, 5_000)
        share = rng.choice([0.05, 0.1, 0.25, 0.5])
        value = rng.choice([None, 0, 3, 100, 10_000])
        got = cap.capped_destroyed(total, wanted, L(share, recent, value))
        assert 0 <= got <= min(total, wanted)
        assert got <= cap.max_by_share(total, share, recent)
        if value is not None:
            assert got <= value
        # the window total never passes the share of the window-start stock
        # (except the single-building minimum on a first strike)
        assert recent + got <= max(int((total + recent) * share), recent + 1)


def test_prices_come_from_the_game_tables():
    assert cap.building_gold("farms") == variables.PROVINCE_UNIT_PRICES["farms_price"]
    assert cap.building_gold("silos") == variables.PROVINCE_UNIT_PRICES["silos_price"]
    assert cap.building_gold("not_a_building") is None
    assert cap.unit_activation_gold("kamikaze_drones", 1000) == 3_500_000
    assert cap.unit_activation_gold("cruise_missiles", 100) == 25_000_000
    assert cap.unit_activation_gold("nonsense", 5) == 0
    assert cap.unit_activation_gold("kamikaze_drones", -3) == 0


class _Db:
    def __init__(self, total=0, fail=False):
        self.total, self.fail, self.sql = total, fail, []

    def execute(self, sql, params=()):
        s = " ".join(sql.split())
        self.sql.append((s, params))
        if self.fail and "war_building_losses" in s:
            raise RuntimeError("no table")

    def fetchone(self):
        return (self.total,)


def test_recent_strike_losses_reads_the_war_history_log():
    db = _Db(total=42)
    assert cap.recent_strike_losses(db, 7, "farms") == 42
    select = [s for s in db.sql if "FROM war_building_losses" in s[0]][0]
    assert "source = 'strike'" in select[0] and select[1] == (7, "farms", 72)


def test_recent_strike_losses_fails_to_zero_and_keeps_the_transaction_usable():
    db = _Db(fail=True)
    assert cap.recent_strike_losses(db, 7, "farms") == 0
    assert any("ROLLBACK TO SAVEPOINT" in s[0] for s in db.sql)


def test_limits_for_is_none_with_the_flag_off_and_reads_nothing(monkeypatch):
    monkeypatch.setattr(cap, "enabled", lambda *a, **k: False)
    db = _Db()
    assert cap.limits_for(db, 1, 2, "farms", "kamikaze_drones", 1000) is None
    assert db.sql == []


def test_limits_for_flag_on(monkeypatch):
    monkeypatch.setattr(cap, "enabled", lambda *a, **k: True)
    got = cap.limits_for(_Db(total=5), 1, 2, "farms", "kamikaze_drones", 1000)
    assert got == L(0.25, 5, 46)
    got = cap.limits_for(_Db(), 1, 2, "silos", "cruise_missiles", 100)
    assert got == L(0.10, 0, 1)  # 500,000,000 / 350,000,000


# --------------------------------------------------------------- local database
needs_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL") or bool(os.getenv("DATABASE_PUBLIC_URL")),
    reason="Needs a LOCAL Postgres in DATABASE_URL (and no DATABASE_PUBLIC_URL)",
)


def _give(db, uid, unit, qty):
    db.execute(
        "INSERT INTO user_military (user_id, unit_id, quantity) "
        "SELECT %s, unit_id, %s FROM unit_dictionary WHERE name = %s",
        (uid, qty, unit),
    )


def _build(db, uid, prov, name, qty):
    db.execute(
        "INSERT INTO user_buildings (user_id, building_id, province_id, quantity) "
        "SELECT %s, building_id, %s, %s FROM building_dictionary WHERE name = %s",
        (uid, prov, qty, name),
    )


def _count(db, uid, name):
    db.execute(
        "SELECT COALESCE(SUM(ub.quantity), 0) FROM user_buildings ub JOIN "
        "building_dictionary bd ON bd.building_id = ub.building_id "
        "WHERE ub.user_id = %s AND bd.name = %s",
        (uid, name),
    )
    return int(db.fetchone()[0])


def _cleanup(ids):
    from database import get_db_connection
    from tests._db_cleanup import purge_users_where

    with get_db_connection() as conn:
        db = conn.cursor()
        for uid in ids:
            db.execute("DELETE FROM wars WHERE attacker=%s OR defender=%s", (uid, uid))
            db.execute("DELETE FROM war_building_losses WHERE victim_id=%s", (uid,))
            for table, col in (
                ("news", "destination_id"),
                ("user_buildings", "user_id"),
                ("user_military", "user_id"),
                ("provinces", "userid"),
                ("referral_active_days", "referred_user_id"),
                ("stats", "id"),
            ):
                db.execute(f"DELETE FROM {table} WHERE {col}=%s", (uid,))
            purge_users_where(db, "id=%s", (uid,))
        conn.commit()


def _world(db, building, qty, provinces=1):
    """Attacker a, target b with `qty` of `building` split over `provinces`, a war."""
    from tests.test_nuclear_strike import _mk_user

    a, _, _ = _mk_user(db, "ba", 1_000_000)
    b, _, b_prov = _mk_user(db, "bb", 1_000_000)
    provs = [b_prov]
    for i in range(1, provinces):
        db.execute(
            "INSERT INTO provinces (userid, provincename, citycount, land, population) "
            "VALUES (%s, %s, 20, 50, 1000000) RETURNING id",
            (b, f"bb-{i}"),
        )
        provs.append(db.fetchone()[0])
    base, extra = divmod(qty, provinces)
    for i, prov in enumerate(provs):
        _build(db, b, prov, building, base + (1 if i < extra else 0))
    db.execute(
        "INSERT INTO wars (attacker, defender, war_type, agressor_message, start_date, "
        "last_visited) VALUES (%s, %s, 'Raze', 'test', extract(epoch from now()), "
        "extract(epoch from now())) RETURNING id",
        (a, b),
    )
    return a, b


def _fire(
    client,
    monkeypatch,
    on,
    route,
    unit,
    field,
    count,
    building,
    qty,
    target=None,
    provinces=1,
    strikes=1,
):
    """Fire `strikes` strikes of `count` units. Returns (status codes, buildings left)."""
    from app_core import missile_pause
    from database import get_db_connection

    monkeypatch.setattr(cap, "enabled", lambda *a, **k: on)
    monkeypatch.setattr(missile_pause, "paused", lambda user_id=None: False)
    monkeypatch.setattr("wars.routes._spend_gasoline", lambda *a, **k: True)
    monkeypatch.setattr(random, "uniform", lambda lo, hi: (lo + hi) / 2)
    ids = []
    try:
        with get_db_connection() as conn:
            db = conn.cursor()
            a, b = _world(db, building, qty, provinces)
            _give(db, a, unit, count * strikes)
            ids = [a, b]
            conn.commit()
        codes = []
        for _ in range(strikes):
            with client.session_transaction() as sess:
                sess["user_id"] = a
            resp = client.post(
                route,
                data={
                    "target_id": str(b),
                    "strike_target": target or building,
                    field: str(count),
                },
            )
            codes.append(resp.status_code)
        with get_db_connection() as conn:
            db = conn.cursor()
            return codes, _count(db, b, building)
    finally:
        _cleanup(ids)


DRONES = dict(route="/drone_strike", unit="kamikaze_drones", field="drones_count")
CRUISE = dict(
    route="/cruise_missile_strike", unit="cruise_missiles", field="missiles_count"
)


@needs_db
def test_drone_strike_flag_off_destroys_everything_it_can(client, monkeypatch):
    # 1000 drones: 700 hits x 2 = 1400 points, 6 per farm = 233 farms
    codes, left = _fire(
        client, monkeypatch, False, **DRONES, count=1000, building="farms", qty=400
    )
    assert codes == [302] and left == 400 - 233


@needs_db
def test_drone_strike_flag_on_is_held_to_twenty_times_its_gold(client, monkeypatch):
    # 3,500,000 gold of drones x 20 = 70,000,000 = 46 farms (not 233, not the 100 share)
    codes, left = _fire(
        client, monkeypatch, True, **DRONES, count=1000, building="farms", qty=400
    )
    assert codes == [302] and left == 400 - 46


@needs_db
def test_flag_on_share_cap_binds_when_the_value_cap_does_not(client, monkeypatch):
    # 100 cruise missiles at 200 steel mills: wanted 80, value 83, share 50
    codes, left = _fire(
        client, monkeypatch, True, **CRUISE, count=100, building="steel_mills", qty=200
    )
    assert codes == [302] and left == 200 - 50


@needs_db
def test_flag_on_a_strike_within_every_cap_is_unchanged(client, monkeypatch):
    # 100 cruise missiles at 1000 steel mills: wanted 80 <= value 83 <= share 250
    off = _fire(
        client,
        monkeypatch,
        False,
        **CRUISE,
        count=100,
        building="steel_mills",
        qty=1000,
    )
    on = _fire(
        client, monkeypatch, True, **CRUISE, count=100, building="steel_mills", qty=1000
    )
    assert off == on == ([302], 1000 - 80)


@needs_db
def test_flag_on_counts_all_provinces(client, monkeypatch):
    codes, left = _fire(
        client,
        monkeypatch,
        True,
        **CRUISE,
        count=100,
        building="steel_mills",
        qty=200,
        provinces=4,
    )
    assert codes == [302] and left == 150  # share of the nation's 200, not per province


@needs_db
def test_flag_on_a_tiny_stock_can_still_lose_one(client, monkeypatch):
    codes, left = _fire(
        client, monkeypatch, True, **DRONES, count=1000, building="farms", qty=3
    )
    assert codes == [302] and left == 2


@needs_db
def test_flag_on_three_strikes_in_a_row_are_capped_together(client, monkeypatch):
    # 5000 drones each (plenty of value and points): the 72h window allows 25% in total
    kw = dict(**DRONES, count=5000, building="farms", qty=1000, strikes=3)
    codes, left_off = _fire(client, monkeypatch, False, **kw)
    # today: the first strike levels the stock, the others find nothing to hit
    assert codes == [302, 400, 400] and left_off == 0
    codes, left_on = _fire(client, monkeypatch, True, **kw)
    assert codes == [302] * 3 and left_on == 750  # 25% in total, not 57.8%


@needs_db
def test_flag_on_silos_are_out_of_reach_of_drones(client, monkeypatch):
    kw = dict(**DRONES, count=1000, building="silos", qty=40, target="silo")
    codes, left = _fire(client, monkeypatch, False, **kw)
    assert codes == [302] and left == 0  # 1400 // 15 = 93, more than the 40 owned
    codes, left = _fire(client, monkeypatch, True, **kw)
    assert codes == [302] and left == 40  # 70,000,000 gold buys 0 of 350,000,000 silos


@needs_db
def test_flag_on_cruise_missiles_can_still_hit_a_silo(client, monkeypatch):
    kw = dict(**CRUISE, count=100, building="silos", qty=40, target="silo")
    codes, left = _fire(client, monkeypatch, True, **kw)
    # 25,000,000 x 20 = 500,000,000 gold = 1 silo (share would allow 4)
    assert codes == [302] and left == 39


@needs_db
def test_strategic_airstrike_is_not_affected_by_this_flag(client, monkeypatch):
    """The strategic airstrike has its own limits (B11); this flag must not touch it."""
    from app_core import missile_pause
    from database import get_db_connection

    monkeypatch.setattr(cap, "enabled", lambda *a, **k: True)
    monkeypatch.setattr(missile_pause, "paused", lambda user_id=None: False)
    monkeypatch.setattr(random, "uniform", lambda lo, hi: (lo + hi) / 2)
    ids = []
    try:
        with get_db_connection() as conn:
            db = conn.cursor()
            a, b = _world(db, "silos", 40)
            _give(db, a, "bombers", 200)
            ids = [a, b]
            conn.commit()
        with client.session_transaction() as sess:
            sess["user_id"] = a
        resp = client.post(
            "/strategic_airstrike",
            data={"target_id": str(b), "strike_target": "silo", "bombers_count": "200"},
        )
        with get_db_connection() as conn:
            db = conn.cursor()
            assert resp.status_code == 302 and _count(db, b, "silos") == 40 - 13
    finally:
        _cleanup(ids)
