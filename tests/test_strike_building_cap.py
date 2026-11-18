"""Cap on the share of one building type a drone / cruise missile strike destroys
(flag strike_building_cap).

Pure functions, then apply_building_damage and the real /drone_strike and
/cruise_missile_strike routes against the local database, flag off and on.
"""

import os
import random

import pytest

from wars import strike_building_cap as cap

pytestmark = pytest.mark.no_server


# ---------------------------------------------------------------------------- pure
def test_flag_key_and_fail_safe(monkeypatch):
    seen = {}

    def fake(key, user_id=None, default=False):
        seen["key"] = key
        return True

    monkeypatch.setattr(cap, "is_on", fake)
    assert cap.enabled(1) is True and seen["key"] == "strike_building_cap"
    assert cap.max_share_for(1) == 0.25

    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(cap, "is_on", boom)
    assert cap.enabled(1) is False and cap.max_share_for(1) is None


def test_default_constants():
    assert cap.STRIKE_BUILDING_MAX_SHARE == 0.25
    assert cap.STRIKE_BUILDING_MIN_PER_STRIKE == 1


@pytest.mark.parametrize(
    "total,allowed",
    [(0, 0), (1, 1), (3, 1), (4, 1), (7, 1), (8, 2), (400, 100), (401, 100)],
)
def test_max_destroyed(total, allowed):
    assert cap.max_destroyed(total) == allowed


def test_capped_destroyed_flag_off_is_the_old_rule():
    assert cap.capped_destroyed(400, 233, None) == 233
    assert cap.capped_destroyed(100, 233, None) == 100  # never more than owned
    assert cap.capped_destroyed(0, 5, None) == 0
    assert cap.capped_destroyed(10, 0, None) == 0


def test_capped_destroyed_flag_on():
    assert cap.capped_destroyed(400, 233, 0.25) == 100
    assert cap.capped_destroyed(400, 50, 0.25) == 50  # a small strike is untouched
    assert cap.capped_destroyed(3, 500, 0.25) == 1  # minimum of one
    assert cap.capped_destroyed(3, 0, 0.25) == 0  # nothing asked, nothing destroyed


def test_never_above_share_or_owned_for_any_input():
    rng = random.Random(5)
    for _ in range(500):
        total = rng.randint(0, 10_000)
        wanted = rng.randint(0, 50_000)
        share = rng.choice([0.05, 0.1, 0.25, 0.5])
        got = cap.capped_destroyed(total, wanted, share)
        assert 0 <= got <= min(total, wanted)
        assert got <= max(1, int(total * share)) or total == 0


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
):
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
            _give(db, a, unit, count)
            ids = [a, b]
            conn.commit()
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
        with get_db_connection() as conn:
            db = conn.cursor()
            return resp.status_code, _count(db, b, building)
    finally:
        _cleanup(ids)


@needs_db
def test_drone_strike_flag_off_destroys_everything_it_can(client, monkeypatch):
    # 1000 drones: 700 hits x 2 = 1400 points, 6 per farm = 233 farms
    code, left = _fire(
        client,
        monkeypatch,
        False,
        "/drone_strike",
        "kamikaze_drones",
        "drones_count",
        1000,
        "farms",
        400,
    )
    assert code == 302 and left == 400 - 233


@needs_db
def test_drone_strike_flag_on_caps_the_share(client, monkeypatch):
    code, left = _fire(
        client,
        monkeypatch,
        True,
        "/drone_strike",
        "kamikaze_drones",
        "drones_count",
        1000,
        "farms",
        400,
    )
    assert code == 302 and left == 400 - 100  # 25% of 400


@needs_db
def test_drone_strike_flag_on_small_strike_is_untouched(client, monkeypatch):
    # 60 drones: 42 hits x 2 = 84 points = 14 farms, far below 25% of 400
    code, left = _fire(
        client,
        monkeypatch,
        True,
        "/drone_strike",
        "kamikaze_drones",
        "drones_count",
        60,
        "farms",
        400,
    )
    assert code == 302 and left == 400 - 14


@needs_db
def test_drone_strike_flag_on_counts_all_provinces(client, monkeypatch):
    # 400 farms spread over 4 provinces: the cap is 25% of the nation's total
    code, left = _fire(
        client,
        monkeypatch,
        True,
        "/drone_strike",
        "kamikaze_drones",
        "drones_count",
        1000,
        "farms",
        400,
        provinces=4,
    )
    assert code == 302 and left == 300


@needs_db
def test_drone_strike_flag_on_a_tiny_stock_still_loses_one(client, monkeypatch):
    code, left = _fire(
        client,
        monkeypatch,
        True,
        "/drone_strike",
        "kamikaze_drones",
        "drones_count",
        1000,
        "farms",
        3,
    )
    assert code == 302 and left == 2


@needs_db
def test_cruise_missile_strike_flag_off_and_on(client, monkeypatch):
    # 100 missiles x 8 = 800 points, 10 per steel mill = 80 mills
    kw = dict(
        route="/cruise_missile_strike",
        unit="cruise_missiles",
        field="missiles_count",
        count=100,
        building="steel_mills",
        qty=200,
    )
    code, left = _fire(client, monkeypatch, False, **kw)
    assert code == 302 and left == 200 - 80
    code, left = _fire(client, monkeypatch, True, **kw)
    assert code == 302 and left == 200 - 50  # 25% of 200


@needs_db
def test_silo_drone_strike_is_capped_too(client, monkeypatch):
    kw = dict(
        route="/drone_strike",
        unit="kamikaze_drones",
        field="drones_count",
        count=1000,
        building="silos",
        qty=40,
        target="silo",
    )
    code, left = _fire(client, monkeypatch, False, **kw)
    assert code == 302 and left == 0  # 1400 // 15 = 93, more than the 40 owned
    code, left = _fire(client, monkeypatch, True, **kw)
    assert code == 302 and left == 30


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
