"""Who can nuke whom (flag nuke_target_rules): the pure can_nuke rules, the plan_strike
wiring, and a real-database check. Flag OFF must change nothing."""

import datetime
import os

import pytest

from wars import nuke_eligibility as ne
from wars.war_range import WAR_RANGE_HIGH, WAR_RANGE_LOW, war_strength

pure = pytest.mark.no_server

OLD = 400.0  # days: an old account
RICH = 1_000_000  # influence well above the protection bar


# ----------------------------------------------------------------- flag / constants
@pure
def test_flag_key_and_fail_safe(monkeypatch):
    seen = {}

    def fake(key, user_id=None, default=False):
        seen["key"] = key
        return True

    monkeypatch.setattr(ne, "is_on", fake)
    assert ne.enabled(1) is True and seen["key"] == "nuke_target_rules"

    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(ne, "is_on", boom)
    assert ne.enabled(1) is False


@pure
def test_constants_and_range_are_the_shared_values():
    assert ne.NUKE_PROTECTION_MIN_INFLUENCE == 100_000
    assert ne.NUKE_PROTECTION_MIN_AGE_DAYS == 14
    # the range is not copied: it is the war range from wars/war_range.py
    assert (WAR_RANGE_LOW, WAR_RANGE_HIGH) == (0.75, 1.33)


# ------------------------------------------------------------------------ range
@pure
@pytest.mark.parametrize(
    "target,ok",
    [(749, False), (750, True), (1000, True), (1330, True), (1331, False), (0, False)],
)
def test_range_is_rechecked_at_launch(target, ok):
    got, reason = ne.can_nuke(1000.0, float(target), RICH, OLD, False)
    assert got is ok
    assert (reason is None) == ok
    if not ok:
        assert "war range" in reason


@pure
def test_range_uses_population_only_so_selling_units_changes_nothing():
    """The gaming case: war range was moved to population because players sold units
    before declaring. war_strength ignores units, so can_nuke inputs cannot be moved by
    selling or buying them."""
    pop = 250_000_000
    assert war_strength(pop, {"soldiers": 10**9, "tanks": 10**6}) == war_strength(
        pop, {}
    )
    assert war_strength(pop) == pop / 1000.0


@pure
def test_a_target_that_fell_out_of_range_since_the_war_began_is_refused():
    # declared at equal size, then the target lost people: 600 < 75% of 1000
    ok, reason = ne.can_nuke(1000.0, 600.0, RICH, OLD, False)
    assert not ok and "outside your war range" in reason


# ------------------------------------------------------------------- protection
@pure
@pytest.mark.parametrize("influence,ok", [(99_999, False), (100_000, True), (0, False)])
def test_protection_by_influence(influence, ok):
    got, reason = ne.can_nuke(1000.0, 1000.0, influence, OLD, False)
    assert got is ok
    if not ok:
        assert "100,000 influence" in reason


@pure
@pytest.mark.parametrize("age,ok", [(0, False), (13, False), (14, True), (400, True)])
def test_protection_by_account_age(age, ok):
    got, reason = ne.can_nuke(1000.0, 1000.0, RICH, float(age), False)
    assert got is ok
    if not ok:
        assert "younger than 14 days" in reason


@pure
def test_unknown_age_does_not_protect():
    assert ne.can_nuke(1000.0, 1000.0, RICH, None, False) == (True, None)


@pure
def test_none_influence_counts_as_zero():
    assert ne.can_nuke(1000.0, 1000.0, None, OLD, False)[0] is False


# ----------------------------------------------------------------- retaliation
@pure
def test_retaliation_is_always_allowed():
    # protected (no influence, brand new) AND out of range: still allowed
    assert ne.can_nuke(1000.0, 1.0, 0, 0.0, True) == (True, None)
    assert ne.can_nuke(0.0, 5_000_000.0, 0, None, True) == (True, None)


@pure
def test_all_good_is_allowed():
    assert ne.can_nuke(1000.0, 1000.0, RICH, OLD, False) == (True, None)


@pure
def test_protection_is_reported_before_range():
    ok, reason = ne.can_nuke(1000.0, 1.0, 0, 0.0, False)
    assert not ok and "protected" in reason


# --------------------------------------------------------------------- account age
@pure
def test_account_age_days():
    today = datetime.date(2026, 11, 19)
    assert ne.account_age_days("2026-11-19", today) == 0
    assert ne.account_age_days("2026-11-05", today) == 14
    assert ne.account_age_days("2026-09-27", today) == 53
    assert ne.account_age_days(" 2026-11-18 ", today) == 1


@pure
@pytest.mark.parametrize("bad", [None, "", "not a date", "19/11/2026", "2026-13-40"])
def test_account_age_unreadable_is_none(bad):
    assert ne.account_age_days(bad, datetime.date(2026, 11, 19)) is None


# ------------------------------------------------------- plan_strike wiring (fakes)
class _FakeDb:
    def execute(self, *a, **k):
        pass

    def fetchall(self):
        return [(1, "Attacker"), (2, "Defender")]

    def fetchone(self):
        return (0,)


def _plan(monkeypatch, *, on, reason=None, retaliation=False, salvo=False):
    from app_core import missile_pause
    from wars import nuclear

    calls = []
    monkeypatch.setattr(nuclear, "_active_war", lambda db, war_id, attacker_id: 2)
    monkeypatch.setattr(nuclear, "fresh_influence", lambda db, uid: 5_000_000)
    monkeypatch.setattr(nuclear, "is_retaliation", lambda *a, **k: retaliation)
    monkeypatch.setattr(nuclear, "_nuke_count", lambda db, uid: 3)
    monkeypatch.setattr(nuclear, "volleys_used", lambda *a, **k: 0)
    monkeypatch.setattr(
        nuclear,
        "enemy_provinces",
        lambda db, eid: [{"id": 10, "population": 1000, "land": 10, "citycount": 2}],
    )
    monkeypatch.setattr(missile_pause, "paused", lambda user_id=None: False)
    monkeypatch.setattr(ne, "enabled", lambda *a, **k: on)

    def fake_check(db, attacker_id, enemy_id, retal):
        calls.append((attacker_id, enemy_id, retal))
        return reason

    monkeypatch.setattr(ne, "check", fake_check)
    plan = nuclear.plan_strike(_FakeDb(), 1, 99, salvo=salvo)
    return plan, calls


@pure
def test_flag_off_plan_strike_is_unchanged_and_never_calls_the_check(monkeypatch):
    plan, calls = _plan(monkeypatch, on=False, reason="should not appear")
    assert plan["blocked"] is None and calls == []


@pure
def test_flag_on_plan_strike_reports_the_refusal(monkeypatch):
    plan, calls = _plan(monkeypatch, on=True, reason="out of range")
    assert plan["blocked"] == "out of range" and calls == [(1, 2, False)]


@pure
def test_flag_on_allowed_launch_stays_unblocked(monkeypatch):
    plan, calls = _plan(monkeypatch, on=True, reason=None)
    assert plan["blocked"] is None and len(calls) == 1


@pure
def test_flag_on_retaliation_is_passed_through_as_retaliation(monkeypatch):
    plan, calls = _plan(monkeypatch, on=True, reason=None, retaliation=True)
    assert calls == [(1, 2, True)] and plan["blocked"] is None


@pure
def test_warheads_inside_a_salvo_are_not_rechecked(monkeypatch):
    plan, calls = _plan(monkeypatch, on=True, reason="out of range", salvo=True)
    assert calls == [] and plan["blocked"] is None


@pure
def test_existing_blocks_win_and_skip_the_check(monkeypatch):
    from wars import nuclear

    plan, calls = _plan(monkeypatch, on=True, reason="out of range")
    assert plan["blocked"] == "out of range"
    # no nukes: the old reason is kept and the new check is not even asked
    monkeypatch.setattr(nuclear, "_nuke_count", lambda db, uid: 0)
    calls.clear()
    plan = nuclear.plan_strike(_FakeDb(), 1, 99)
    assert plan["blocked"] == "You don't have any nukes." and calls == []


@pure
def test_the_pause_message_still_wins_over_the_new_rules(monkeypatch):
    from app_core import missile_pause

    _plan(monkeypatch, on=True, reason="out of range")
    from wars import nuclear

    monkeypatch.setattr(missile_pause, "paused", lambda user_id=None: True)
    plan = nuclear.plan_strike(_FakeDb(), 1, 99)
    assert plan["blocked"] == missile_pause.MESSAGE


@pure
def test_check_reads_nothing_for_a_retaliation():
    class Boom:
        def execute(self, *a, **k):
            raise AssertionError("retaliation must not touch the database")

    assert ne.check(Boom(), 1, 2, True) is None


@pure
def test_check_uses_the_pure_rules(monkeypatch):
    monkeypatch.setattr(
        ne, "get_user_war_strength", lambda db, uid: {1: 1000.0, 2: 500.0}[uid]
    )
    monkeypatch.setattr("wars.nuclear.fresh_influence", lambda db, uid: 5_000_000)

    class Db:
        def execute(self, *a, **k):
            pass

        def fetchone(self):
            return ("2026-01-01",)

    assert "war range" in ne.check(Db(), 1, 2, False)
    monkeypatch.setattr(ne, "get_user_war_strength", lambda db, uid: 1000.0)
    assert ne.check(Db(), 1, 2, False) is None


# --------------------------------------------------------------- real database
needs_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL") or bool(os.getenv("DATABASE_PUBLIC_URL")),
    reason="Needs a LOCAL Postgres in DATABASE_URL (and no DATABASE_PUBLIC_URL)",
)


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


def _world(db, a_pop, b_pop, b_date=None, first_strike_by=None):
    from tests.test_nuclear_strike import _give_nukes, _mk_user

    a, _, _ = _mk_user(db, "na", a_pop)
    b, _, _ = _mk_user(db, "nb", b_pop)
    if b_date:
        db.execute("UPDATE users SET date=%s WHERE id=%s", (b_date, b))
    _give_nukes(db, a, 2)
    _give_nukes(db, b, 2)
    db.execute(
        "INSERT INTO wars (attacker, defender, war_type, agressor_message, start_date, "
        "last_visited) VALUES (%s, %s, 'Raze', 'test', extract(epoch from now()), "
        "extract(epoch from now())) RETURNING id",
        (a, b),
    )
    war_id = db.fetchone()[0]
    if first_strike_by:
        # b already nuked a in this war: a's launch is a retaliation
        first, other = (b, a) if first_strike_by == "b" else (a, b)
        db.execute(
            "INSERT INTO nuclear_strikes (war_id, attacker_id, target_id, province_id, "
            "province_name, launched_at, recovers_at, is_retaliation, influence_before, "
            "influence_cost, damage_multiplier, deaths, cities_destroyed, "
            "buildings_destroyed, happiness_lost) SELECT %s, %s, %s, p.id, p.provincename, "
            "now(), now() + interval '7 days', FALSE, 1, 0, 1, 0, 0, 0, 0 "
            "FROM provinces p WHERE p.userid = %s LIMIT 1",
            (war_id, first, other, other),
        )
    return a, b, war_id


def _db_plan(on, a, b, war_id, monkeypatch, salvo=False):
    from database import get_db_connection, query_cache
    from wars import nuclear

    monkeypatch.setattr(ne, "enabled", lambda *x, **k: on)
    query_cache.invalidate(pattern="influence_")
    with get_db_connection() as conn:
        db = conn.cursor()
        plan = nuclear.plan_strike(db, a, war_id, salvo=salvo)
        conn.rollback()
    return plan


@needs_db
def test_db_out_of_range_target_is_refused_only_with_the_flag(monkeypatch):
    from database import get_db_connection

    ids = []
    try:
        with get_db_connection() as conn:
            db = conn.cursor()
            # attacker 300M people (1.5M influence), target 10M: far below 75%
            a, b, war_id = _world(db, 300_000_000, 10_000_000, first_strike_by="b")
            ids = [a, b]
            conn.commit()
        # b nuked first, so this launch is a retaliation: allowed even when out of range
        assert _db_plan(True, a, b, war_id, monkeypatch)["blocked"] is None
    finally:
        _cleanup(ids)
    ids = []
    try:
        with get_db_connection() as conn:
            db = conn.cursor()
            a, b, war_id = _world(db, 300_000_000, 10_000_000)
            ids = [a, b]
            conn.commit()
        assert (
            _db_plan(False, a, b, war_id, monkeypatch)["blocked"] is None
        )  # old behaviour
        blocked = _db_plan(True, a, b, war_id, monkeypatch)["blocked"]
        assert (
            blocked and "protected" in blocked
        )  # 10M people = 50,000 influence < 100,000
        # inside a salvo the warhead is not rechecked
        assert _db_plan(True, a, b, war_id, monkeypatch, salvo=True)["blocked"] is None
    finally:
        _cleanup(ids)


@needs_db
def test_db_in_range_old_target_is_allowed_and_a_new_account_is_protected(monkeypatch):
    from database import get_db_connection

    today = str(datetime.date.today())
    ids = []
    try:
        with get_db_connection() as conn:
            db = conn.cursor()
            a, b, war_id = _world(
                db, 300_000_000, 300_000_000
            )  # same size, old account
            ids = [a, b]
            conn.commit()
        assert _db_plan(True, a, b, war_id, monkeypatch)["blocked"] is None
        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute("UPDATE users SET date=%s WHERE id=%s", (today, b))
            conn.commit()
        blocked = _db_plan(True, a, b, war_id, monkeypatch)["blocked"]
        assert blocked and "younger than 14 days" in blocked
        assert _db_plan(False, a, b, war_id, monkeypatch)["blocked"] is None
    finally:
        _cleanup(ids)


@needs_db
def test_db_a_target_that_shrank_out_of_range_after_the_war_began(monkeypatch):
    from database import get_db_connection

    ids = []
    try:
        with get_db_connection() as conn:
            db = conn.cursor()
            a, b, war_id = _world(db, 300_000_000, 300_000_000)
            ids = [a, b]
            conn.commit()
        assert _db_plan(True, a, b, war_id, monkeypatch)["blocked"] is None
        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute(
                "UPDATE provinces SET population = 180000000 WHERE userid=%s", (b,)
            )
            conn.commit()
        blocked = _db_plan(True, a, b, war_id, monkeypatch)["blocked"]
        assert blocked and "outside your war range" in blocked  # 60% of the attacker
    finally:
        _cleanup(ids)
