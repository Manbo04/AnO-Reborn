"""Strategic airstrike limits (flag strategic_airstrike_limits).

Pure functions first, then the real /strategic_airstrike route against the local
database with the flag off and on (random rolls fixed at the middle of their range).
"""

import os
import random

import pytest

from wars import airstrike_limits as al

pytestmark = pytest.mark.no_server


# ---------------------------------------------------------------------------- pure
def test_flag_key_and_fail_safe(monkeypatch):
    seen = {}

    def fake(key, user_id=None, default=False):
        seen["key"] = key
        return True

    monkeypatch.setattr(al, "is_on", fake)
    assert al.enabled(1) is True and seen["key"] == "strategic_airstrike_limits"

    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(al, "is_on", boom)
    assert al.enabled(1) is False


def test_default_constants():
    assert al.STRATEGIC_AIRSTRIKE_AP_COST == 2
    assert al.STRATEGIC_AIRSTRIKE_MAX_SILO_SHARE == 0.25
    assert al.STRATEGIC_AIRSTRIKE_TECH_THRESHOLD == 150
    assert al.STRATEGIC_AIRSTRIKE_TECH_THRESHOLD_OFF == 50  # today's bar


@pytest.mark.parametrize(
    "total,allowed",
    [(0, 0), (1, 1), (3, 1), (4, 1), (8, 2), (40, 10), (41, 10), (1000, 250)],
)
def test_max_silos_per_strike(total, allowed):
    assert al.max_silos_per_strike(total) == allowed


def test_silo_damage_points_limits_the_number_destroyed():
    # 200 points would destroy 13 of 40 silos (15 points each); the cap keeps it at 10
    assert al.silo_damage_points(40, 200) == 150
    assert int(al.silo_damage_points(40, 200) // 15) == 10
    # a small strike is unchanged
    assert al.silo_damage_points(40, 40) == 40
    # tiny stock: still can destroy one
    assert int(al.silo_damage_points(2, 500) // 15) == 1
    assert al.silo_damage_points(0, 500) == 0


def test_silo_damage_points_never_destroys_more_than_allowed_for_any_input():
    rng = random.Random(1)
    for _ in range(500):
        total = rng.randint(0, 5000)
        power = rng.uniform(0, 100_000)
        pts = al.silo_damage_points(total, power)
        destroyed = min(total, int(pts // 15))
        assert destroyed <= al.max_silos_per_strike(total)
        assert pts <= power


def test_tech_threshold_depends_on_the_flag():
    assert al.tech_threshold(False) == 50
    assert al.tech_threshold(True) == 150


# ------------------------------------------------------------- route (local database)
needs_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL") or bool(os.getenv("DATABASE_PUBLIC_URL")),
    reason="Needs a LOCAL Postgres in DATABASE_URL (and no DATABASE_PUBLIC_URL)",
)


def _setup(db, silos, bombers, fighters=0, tech=False, ap=6):
    from tests.test_nuclear_strike import _mk_user

    a, _, _ = _mk_user(db, "aa", 1_000_000)
    b, _, b_prov = _mk_user(db, "ab", 1_000_000)
    for uid, name, qty in ((a, "bombers", bombers), (b, "fighters", fighters)):
        if qty:
            db.execute(
                "INSERT INTO user_military (user_id, unit_id, quantity) "
                "SELECT %s, unit_id, %s FROM unit_dictionary WHERE name = %s",
                (uid, qty, name),
            )
    if silos:
        db.execute(
            "INSERT INTO user_buildings (user_id, building_id, province_id, quantity) "
            "SELECT %s, building_id, %s, %s FROM building_dictionary WHERE name = 'silos'",
            (b, b_prov, silos),
        )
    if tech:
        db.execute(
            "INSERT INTO user_tech (user_id, tech_id, is_unlocked) "
            "SELECT %s, tech_id, TRUE FROM tech_dictionary "
            "WHERE name = 'nuclear_testing_facility'",
            (b,),
        )
    db.execute(
        "INSERT INTO wars (attacker, defender, war_type, agressor_message, start_date, "
        "last_visited, attacker_air_ap) VALUES (%s, %s, 'Raze', 'test', "
        "extract(epoch from now()), extract(epoch from now()), %s) RETURNING id",
        (a, b, ap),
    )
    return a, b, db.fetchone()[0]


def _state(db, a, b, war_id):
    db.execute(
        "SELECT COALESCE(SUM(ub.quantity), 0) FROM user_buildings ub JOIN "
        "building_dictionary bd ON bd.building_id = ub.building_id "
        "WHERE ub.user_id = %s AND bd.name = 'silos'",
        (b,),
    )
    silos = int(db.fetchone()[0])
    db.execute(
        "SELECT COALESCE(SUM(um.quantity), 0) FROM user_military um JOIN unit_dictionary "
        "ud ON ud.unit_id = um.unit_id WHERE um.user_id = %s AND ud.name = 'bombers'",
        (a,),
    )
    bombers = int(db.fetchone()[0])
    db.execute("SELECT attacker_air_ap FROM wars WHERE id = %s", (war_id,))
    ap = int(db.fetchone()[0])
    db.execute(
        "SELECT ut.is_unlocked FROM user_tech ut JOIN tech_dictionary td ON "
        "td.tech_id = ut.tech_id WHERE ut.user_id = %s AND "
        "td.name = 'nuclear_testing_facility'",
        (b,),
    )
    row = db.fetchone()
    return {
        "silos": silos,
        "bombers": bombers,
        "ap": ap,
        "tech": row[0] if row else None,
    }


def _cleanup(ids):
    from database import get_db_connection
    from tests._db_cleanup import purge_users_where

    with get_db_connection() as conn:
        db = conn.cursor()
        for uid in ids:
            for sql in (
                "DELETE FROM wars WHERE attacker=%s OR defender=%s",
                "DELETE FROM news WHERE destination_id=%s",
                "DELETE FROM user_tech WHERE user_id=%s",
                "DELETE FROM user_buildings WHERE user_id=%s",
                "DELETE FROM user_military WHERE user_id=%s",
                "DELETE FROM provinces WHERE userid=%s",
                "DELETE FROM referral_active_days WHERE referred_user_id=%s",
                "DELETE FROM stats WHERE id=%s",
            ):
                db.execute(sql, (uid, uid) if sql.count("%s") == 2 else (uid,))
            purge_users_where(db, "id=%s", (uid,))
        conn.commit()


def _strike(
    client,
    monkeypatch,
    on,
    silos,
    bombers_sent,
    bombers=None,
    strikes=1,
    target="silo",
    **setup,
):
    """Fire `strikes` strategic airstrikes through the real route. Returns
    (status codes, state after)."""
    from app_core import missile_pause
    from database import get_db_connection

    monkeypatch.setattr(al, "enabled", lambda *a, **k: on)
    monkeypatch.setattr(missile_pause, "paused", lambda user_id=None: False)
    monkeypatch.setattr(random, "uniform", lambda lo, hi: (lo + hi) / 2)  # 1.0 power
    ids = []
    try:
        with get_db_connection() as conn:
            db = conn.cursor()
            a, b, war_id = _setup(
                db, silos, bombers if bombers is not None else bombers_sent, **setup
            )
            ids = [a, b]
            conn.commit()
        codes = []
        for _ in range(strikes):
            with client.session_transaction() as sess:
                sess["user_id"] = a
            resp = client.post(
                "/strategic_airstrike",
                data={
                    "target_id": str(b),
                    "strike_target": target,
                    "bombers_count": str(bombers_sent),
                },
            )
            codes.append(resp.status_code)
        with get_db_connection() as conn:
            db = conn.cursor()
            return codes, _state(db, a, b, war_id)
    finally:
        _cleanup(ids)


@needs_db
def test_flag_off_airstrike_is_unchanged(client, monkeypatch):
    codes, st = _strike(client, monkeypatch, False, silos=40, bombers_sent=200)
    assert codes == [302]
    assert st["silos"] == 40 - 13  # 200 points // 15, no cap
    assert st["ap"] == 6  # no action points charged
    assert st["bombers"] == 200  # none shot down (no fighters)


@needs_db
def test_flag_off_can_repeat_without_limit(client, monkeypatch):
    codes, st = _strike(
        client, monkeypatch, False, silos=39, bombers_sent=200, strikes=3
    )
    assert codes == [302, 302, 302] and st["silos"] == 0 and st["ap"] == 6


@needs_db
def test_flag_on_charges_air_ap_and_caps_the_silos(client, monkeypatch):
    codes, st = _strike(client, monkeypatch, True, silos=40, bombers_sent=200)
    assert codes == [302]
    assert st["silos"] == 40 - 10  # at most 25% of 40
    assert st["ap"] == 6 - al.STRATEGIC_AIRSTRIKE_AP_COST
    assert st["bombers"] == 200


@needs_db
def test_flag_on_runs_out_of_action_points(client, monkeypatch):
    # 6 AP at 2 per strike: three strikes land, the fourth is refused and costs nothing
    codes, st = _strike(
        client, monkeypatch, True, silos=1000, bombers_sent=50, strikes=4
    )
    assert codes == [302, 302, 302, 400]
    assert st["ap"] == 0
    assert st["silos"] == 1000 - 3 * 3  # 50 points // 15 = 3 silos per strike


@needs_db
def test_flag_on_refused_strike_does_not_charge_ap(client, monkeypatch):
    # not enough bombers: refused before the action points are spent
    codes, st = _strike(
        client, monkeypatch, True, silos=40, bombers_sent=200, bombers=10
    )
    assert codes == [400] and st["ap"] == 6 and st["silos"] == 40


@needs_db
def test_flag_on_a_small_stock_can_still_lose_one_silo(client, monkeypatch):
    codes, st = _strike(client, monkeypatch, True, silos=3, bombers_sent=200)
    assert codes == [302] and st["silos"] == 2


@needs_db
def test_flag_off_tech_falls_to_50_points_flag_on_needs_150(client, monkeypatch):
    kw = dict(silos=0, tech=True, target="nuclear_testing_facility")
    _, off = _strike(client, monkeypatch, False, bombers_sent=100, **kw)
    assert off["tech"] is False  # 100 points >= 50: gone for good
    _, on = _strike(client, monkeypatch, True, bombers_sent=100, **kw)
    assert on["tech"] is True  # 100 < 150: survives
    _, on = _strike(client, monkeypatch, True, bombers_sent=160, **kw)
    assert on["tech"] is False  # 160 >= 150


@needs_db
def test_fighters_still_defend_with_the_flag_on(client, monkeypatch):
    # fighters 500 x 1.0 shoot down all 200 bombers: nothing is destroyed
    codes, st = _strike(
        client, monkeypatch, True, silos=40, bombers_sent=200, fighters=500
    )
    assert codes == [302] and st["silos"] == 40 and st["bombers"] == 0
