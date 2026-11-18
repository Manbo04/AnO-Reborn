"""ICBM unit-destruction limits (flag icbm_damage_limits).

Pure math, then Military.special_fight itself with the database faked out (there were
no tests for special_fight before). Flag off must keep today's behaviour, quirks
included, and the flag must only touch ICBMs.
"""

import pytest

from app_core.military import icbm_damage as ic

pytestmark = pytest.mark.no_server

DMG = 1000  # units.IcbmUnit.damage


# --------------------------------------------------------------------- pure math
def test_flag_key_and_fail_safe(monkeypatch):
    seen = {}

    def fake(key, user_id=None, default=False):
        seen["key"] = key
        return True

    monkeypatch.setattr(ic, "is_on", fake)
    assert ic.enabled(1) is True and seen["key"] == "icbm_damage_limits"

    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(ic, "is_on", boom)
    assert ic.enabled(1) is False


def test_default_constants():
    assert ic.ICBM_MAX_UNIT_SHARE == 0.25
    assert ic.ICBM_MIN_DIVISOR == 1.0


@pytest.mark.parametrize("fired", [1, 2, 5, 10])
def test_legacy_grows_with_the_square(fired):
    one = ic.legacy_destruction(DMG * 1, 0, 1, 0.4)
    assert one == pytest.approx(400)
    assert ic.legacy_destruction(DMG * fired, 0, fired, 0.4) == pytest.approx(
        400 * fired * fired
    )


@pytest.mark.parametrize("fired", [1, 2, 5, 10])
def test_limited_grows_linearly_when_uncapped(fired):
    big = 10_000_000  # so large that the share cap never bites
    got = ic.limited_destruction(DMG * fired, 0, fired, 0.4, big)
    assert got == pytest.approx(400 * fired)


def test_one_icbm_is_the_same_flag_on_or_off_when_the_cap_is_not_reached():
    # 1 ICBM at rate 0.4 destroys 400 either way against a big stack
    assert ic.limited_destruction(DMG, 0, 1, 0.4, 10_000) == pytest.approx(
        ic.legacy_destruction(DMG, 0, 1, 0.4)
    )


def test_share_cap_limits_one_strike():
    # 50 destroyers: 2 ICBMs used to wipe them all, now at most 25%
    assert ic.limited_destruction(DMG * 2, 0, 2, 0.5, 50) == pytest.approx(12.5)
    assert ic.limited_destruction(DMG * 10, 0, 10, 0.5, 50) == pytest.approx(12.5)
    # custom share
    assert ic.limited_destruction(DMG * 2, 0, 2, 0.5, 50, max_share=0.1) == 5


def test_iron_dome_survivors_scale_the_damage_down_first():
    full = ic.limited_destruction(DMG * 4, 0, 4, 0.4, 10_000, surviving=1.0)
    half = ic.limited_destruction(DMG * 4, 0, 4, 0.4, 10_000, surviving=0.5)
    none = ic.limited_destruction(DMG * 4, 0, 4, 0.4, 10_000, surviving=0.0)
    assert half == pytest.approx(full / 2) and none == 0
    # and surviving can never be used to go above the damage
    assert ic.limited_destruction(
        DMG, 0, 1, 0.4, 10_000, surviving=3.0
    ) == pytest.approx(400)


def test_zero_inputs_destroy_nothing():
    assert ic.limited_destruction(DMG, 0, 0, 0.4, 100) == 0
    assert ic.limited_destruction(DMG, 0, 1, 0.4, 0) == 0
    assert ic.limited_destruction(0, 0, 1, 0.4, 100) == 0


def test_submarine_bonus_no_longer_makes_destruction_negative():
    """IcbmUnit.attack returns bonus -5 per missile against submarines, so the old
    divisor (1 + bonus) is negative and the old destruction is NEGATIVE."""
    import units

    effects = units.IcbmUnit(2).attack("submarines")
    assert effects == [2000, -10]
    assert ic.legacy_destruction(effects[0], effects[1], 2, 0.4) < 0
    got = ic.limited_destruction(effects[0], effects[1], 2, 0.4, 100_000)
    assert got == pytest.approx(0.4 * 2000)  # divisor floored at 1: like any target


@pytest.mark.parametrize("amount", [1, 7, 50, 1000, 10**6])
@pytest.mark.parametrize("fired", [1, 2, 3, 5, 20, 200])
@pytest.mark.parametrize("target", ["destroyers", "tanks", "submarines"])
def test_never_negative_and_never_above_the_share(amount, fired, target):
    import units

    eff = units.IcbmUnit(fired).attack(target)
    for rate in (0.3, 0.4, 0.5):
        for surviving in (0.0, 0.5, 1.0):
            got = ic.limited_destruction(eff[0], eff[1], fired, rate, amount, surviving)
            assert 0 <= got <= ic.ICBM_MAX_UNIT_SHARE * amount + 1e-9


# ------------------------------------------------------------- special_fight itself
class _Cursor:
    def execute(self, *a, **k):
        pass

    def fetchone(self):
        return (77,)  # a province / unit id: any value works

    def fetchall(self):
        return []


class _Conn:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return _Cursor()

    def commit(self):
        pass


def _fight(
    monkeypatch,
    *,
    on,
    fired,
    owned,
    target="destroyers",
    rate=0.4,
    dome=0,
    special="icbms",
):
    """Run the real Military.special_fight with the DB faked. Returns (destroyed, defender)."""
    import units
    from attack_scripts import Nations
    from app_core.military import iron_dome

    monkeypatch.setattr(ic, "enabled", lambda *a, **k: on)
    monkeypatch.setattr(Nations, "get_db_connection", lambda *a, **k: _Conn())
    monkeypatch.setattr(units, "get_db_connection", lambda *a, **k: _Conn())
    monkeypatch.setattr(units, "get_unusable_units", lambda uid: set())
    monkeypatch.setattr(
        Nations.Military,
        "get_particular_units_list",
        staticmethod(lambda c, u: [owned]),
    )
    monkeypatch.setattr(Nations.random, "uniform", lambda lo, hi: rate)
    monkeypatch.setattr(
        iron_dome,
        "roll_intercepts",
        lambda db, did, count, kind, province_id=None: dome,
    )
    monkeypatch.setattr(
        Nations.Nation, "get_public_works", classmethod(lambda c, p: {})
    )
    monkeypatch.setattr(
        Nations.Military, "infrastructure_damage", staticmethod(lambda *a, **k: {})
    )
    attacker = units.Units(
        1, {special: fired}, selected_units_list=[special], war_id=None
    )
    defender = units.Units(2, {target: owned}, selected_units_list=[target])
    out = Nations.Military.special_fight(attacker, defender, target)
    destroyed = out[0][target]
    return destroyed, defender


def test_special_fight_flag_off_is_the_old_square_growth(monkeypatch):
    # rate 0.4: 1 ICBM = 400 units, 2 = 1,600 (the square), capped only by what exists
    assert _fight(monkeypatch, on=False, fired=1, owned=10_000)[0] == 400
    assert _fight(monkeypatch, on=False, fired=2, owned=10_000)[0] == 1600
    assert _fight(monkeypatch, on=False, fired=5, owned=100_000)[0] == 10_000
    # the "2 ICBMs took out my 50 destroyers" report
    assert _fight(monkeypatch, on=False, fired=2, owned=50)[0] == 50


def test_special_fight_flag_on_is_linear_and_capped(monkeypatch):
    assert _fight(monkeypatch, on=True, fired=1, owned=10_000)[0] == 400
    assert _fight(monkeypatch, on=True, fired=2, owned=10_000)[0] == 800
    assert _fight(monkeypatch, on=True, fired=5, owned=100_000)[0] == 2000
    # 50 destroyers: 2 ICBMs now take at most 25%: floor(12.5) = 12
    destroyed, defender = _fight(monkeypatch, on=True, fired=2, owned=50)
    assert destroyed == 12 and defender.selected_units["destroyers"] == 38
    # 10,000 units, 40 ICBMs: capped at 25%
    assert _fight(monkeypatch, on=True, fired=40, owned=10_000)[0] == 2500


def test_special_fight_iron_dome_still_applies_with_the_flag_on(monkeypatch):
    # 4 fired, 2 shot down: half the damage
    assert _fight(monkeypatch, on=True, fired=4, owned=100_000, dome=2)[0] == 800
    assert _fight(monkeypatch, on=True, fired=4, owned=100_000, dome=4)[0] == 0
    # old behaviour with the same dome result: 400*4*4*0.5
    assert _fight(monkeypatch, on=False, fired=4, owned=100_000, dome=2)[0] == 3200


def test_special_fight_flag_off_submarines_get_negative_destruction(monkeypatch):
    """Today's quirk (flag off, kept as is): ICBMs at submarines ADD submarines."""
    destroyed, defender = _fight(
        monkeypatch, on=False, fired=1, owned=100, target="submarines"
    )
    assert destroyed < 0 and defender.selected_units["submarines"] > 100


def test_special_fight_flag_on_submarines_are_hit_like_any_target(monkeypatch):
    destroyed, defender = _fight(
        monkeypatch, on=True, fired=1, owned=100, target="submarines"
    )
    assert destroyed == 25 and defender.selected_units["submarines"] == 75  # share cap


def test_flag_does_not_touch_other_special_units(monkeypatch):
    """The legacy nukes branch of special_fight is not an ICBM strike: unchanged."""
    off = _fight(monkeypatch, on=False, fired=2, owned=10_000, special="nukes")[0]
    on = _fight(monkeypatch, on=True, fired=2, owned=10_000, special="nukes")[0]
    assert off == on


# ------------------------------------------------------------------ DB (local only)
import os  # noqa: E402

needs_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL") or bool(os.getenv("DATABASE_PUBLIC_URL")),
    reason="Needs a LOCAL Postgres in DATABASE_URL (and no DATABASE_PUBLIC_URL)",
)


@needs_db
def test_db_negative_casualties_add_units_today():
    """Confirms against a real database that the old negative destruction ADDS units
    (this is why the flag floors the divisor)."""
    import units
    from database import get_db_connection
    from tests._db_cleanup import purge_users_where
    from tests.test_nuclear_strike import _mk_user

    uid = None
    try:
        with get_db_connection() as conn:
            db = conn.cursor()
            uid, _, _ = _mk_user(db, "icbm", 1_000_000)
            db.execute(
                "INSERT INTO user_military (user_id, unit_id, quantity) "
                "SELECT %s, unit_id, 100 FROM unit_dictionary WHERE name = 'submarines'",
                (uid,),
            )
            conn.commit()
        defender = units.Units(
            uid, {"submarines": 100}, selected_units_list=["submarines"]
        )
        defender.casualties("submarines", -50)
        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute(
                "SELECT um.quantity FROM user_military um JOIN unit_dictionary ud "
                "ON ud.unit_id = um.unit_id WHERE um.user_id = %s AND ud.name = 'submarines'",
                (uid,),
            )
            assert db.fetchone()[0] == 150
    finally:
        if uid:
            with get_db_connection() as conn:
                db = conn.cursor()
                db.execute("DELETE FROM user_military WHERE user_id=%s", (uid,))
                db.execute("DELETE FROM provinces WHERE userid=%s", (uid,))
                db.execute(
                    "DELETE FROM referral_active_days WHERE referred_user_id=%s", (uid,)
                )
                db.execute("DELETE FROM stats WHERE id=%s", (uid,))
                purge_users_where(db, "id=%s", (uid,))
                conn.commit()
