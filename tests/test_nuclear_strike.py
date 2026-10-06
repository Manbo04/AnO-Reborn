"""Nuclear strike rework (2026-09-27): blast math + full two-step launch flow.

DB tests create throwaway users/war rows and delete them in `finally`. Run
against a local Postgres only:
    env -u DATABASE_PUBLIC_URL DATABASE_URL=postgresql://...local... pytest
"""

import os
import re
import uuid

import pytest

from wars import nuclear as nk
from tests._db_cleanup import purge_users_where


# --- pure math --------------------------------------------------------------

def test_dense_province_loses_more_than_sprawling_one():
    dense = nk.blast_profile(land=10, cities=20)
    sprawl = nk.blast_profile(land=2000, cities=20)
    assert dense["death_frac"] > sprawl["death_frac"]


def test_more_land_per_city_means_fewer_deaths():
    fracs = [nk.blast_profile(land=land, cities=30)["death_frac"] for land in (10, 50, 200, 1000)]
    assert fracs == sorted(fracs, reverse=True)


def test_huge_province_is_not_mostly_wiped():
    huge = nk.blast_profile(land=750, cities=760)  # a big late-game province
    assert huge["death_frac"] < 0.1
    assert nk.blast_profile(land=1, cities=1)["death_frac"] <= nk.POP_LETHALITY


def test_repeat_strikes_decay():
    assert nk.repeat_multiplier([]) == 1
    assert nk.repeat_multiplier([0]) == pytest.approx(0.5)
    assert nk.repeat_multiplier([0, 0]) == pytest.approx(0.25)
    assert nk.repeat_multiplier([36]) == pytest.approx(0.5 ** 0.5)
    assert nk.repeat_multiplier([72]) == 1
    assert nk.repeat_multiplier([100]) == 1


def test_influence_cost_rates():
    assert nk.influence_cost(2_000_000, False) == 1_000_000
    assert nk.influence_cost(2_000_000, True) == 500_000
    # compounding: the second launch takes half of what's left
    left = 2_000_000 - nk.influence_cost(2_000_000, False)
    assert nk.influence_cost(left, False) == 500_000


def test_strike_damage_proportional():
    prov = {"population": 10_000_000, "land": 50, "citycount": 20, "happiness": 80}
    full = nk.strike_damage(prov, 1.0)
    half = nk.strike_damage(prov, 0.5)
    assert 0 < full["deaths"] < prov["population"]
    assert half["deaths"] == pytest.approx(full["deaths"] / 2, rel=0.01)
    assert full["happiness_lost"] == nk.HAPPINESS_HIT
    assert half["happiness_lost"] == nk.HAPPINESS_HIT // 2


# --- DB flow ----------------------------------------------------------------

needs_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL") or bool(os.getenv("DATABASE_PUBLIC_URL")),
    reason="Needs a LOCAL Postgres in DATABASE_URL (and no DATABASE_PUBLIC_URL)",
)


def _mk_user(db, tag, population):
    name = f"nuketest_{tag}_{uuid.uuid4().hex[:6]}"
    db.execute(
        "INSERT INTO users (username, email, date, hash, auth_type) "
        "VALUES (%s, %s, '2026-09-27', '', 'normal') RETURNING id",
        (name, f"{name}@example.test"),
    )
    uid = db.fetchone()[0]
    db.execute("INSERT INTO stats (id, location, gold) VALUES (%s, 'Grassland', 0)", (uid,))
    db.execute(
        "INSERT INTO provinces (userid, provincename, citycount, land, population, happiness, "
        "pop_working) VALUES (%s, %s, 20, 50, %s, 80, %s) RETURNING id",
        (uid, f"{tag}-core", population, population // 2),
    )
    return uid, name, db.fetchone()[0]


def _give_nukes(db, uid, n):
    db.execute(
        "INSERT INTO user_military (user_id, unit_id, quantity) "
        "SELECT %s, unit_id, %s FROM unit_dictionary WHERE name = 'nukes' "
        "ON CONFLICT (user_id, unit_id) DO UPDATE SET quantity = EXCLUDED.quantity",
        (uid, n),
    )


def _login(client, uid):
    with client.session_transaction() as sess:
        sess["user_id"] = uid


def _review_and_launch(client, war_id, province_id):
    r = client.post(f"/nuclear_strike/{war_id}/review", data={"province_id": province_id})
    assert r.status_code == 200, r.data[:500]
    token = re.search(rb'name="token" value="([^"]+)"', r.data).group(1).decode()
    return client.post(
        f"/nuclear_strike/{war_id}/launch",
        data={"province_id": province_id, "token": token, "confirm_launch": "yes"},
    ), token


@needs_db
def test_full_launch_flow(client):
    from database import get_db_connection, query_cache

    ids = []
    try:
        with get_db_connection() as conn:
            db = conn.cursor()
            # attacker: 300M pop -> 1.5M influence (above the 1M bar)
            a, a_name, a_prov = _mk_user(db, "a", 300_000_000)
            b, b_name, b_prov = _mk_user(db, "b", 10_000_000)  # well under 1M
            ids = [a, b]
            _give_nukes(db, a, 3)
            _give_nukes(db, b, 1)
            db.execute(
                "INSERT INTO user_buildings (user_id, building_id, province_id, quantity) "
                "SELECT %s, building_id, %s, 100 FROM building_dictionary WHERE name = 'farms'",
                (b, b_prov),
            )
            db.execute(
                "INSERT INTO wars (attacker, defender, war_type, agressor_message, start_date, last_visited) "
                "VALUES (%s, %s, 'Raze', 'test', extract(epoch from now()), extract(epoch from now())) RETURNING id",
                (a, b),
            )
            war_id = db.fetchone()[0]
            conn.commit()
        query_cache.invalidate(pattern="influence_")

        # B can't first-strike: under 1M influence
        _login(client, b)
        r = client.get(f"/nuclear_strike/{war_id}")
        assert r.status_code == 200 and b"at least 1,000,000 influence" in r.data
        r = client.post(f"/nuclear_strike/{war_id}/review", data={"province_id": a_prov})
        assert r.status_code == 400

        # A: planner renders, launch without a token is refused
        _login(client, a)
        r = client.get(f"/nuclear_strike/{war_id}")
        assert r.status_code == 200 and b"a-core" not in r.data and b"b-core" in r.data
        r = client.post(
            f"/nuclear_strike/{war_id}/launch",
            data={"province_id": b_prov, "token": "x", "confirm_launch": "yes"},
        )
        assert r.status_code == 400
        # A can't target its own province
        r = client.post(f"/nuclear_strike/{war_id}/review", data={"province_id": a_prov})
        assert r.status_code == 400

        with get_db_connection() as conn:
            db = conn.cursor()
            infl_before = nk.fresh_influence(db, a)
        assert infl_before >= 1_000_000

        r, token = _review_and_launch(client, war_id, b_prov)
        assert r.status_code == 200 and b"Nuclear Strike Report" in r.data
        # the token is single-use
        r2 = client.post(
            f"/nuclear_strike/{war_id}/launch",
            data={"province_id": b_prov, "token": token, "confirm_launch": "yes"},
        )
        assert r2.status_code == 400

        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute("SELECT population, citycount, happiness, pop_working FROM provinces WHERE id=%s", (b_prov,))
            pop, cities, happy, working = db.fetchone()
            expected = nk.strike_damage(
                {"population": 10_000_000, "land": 50, "citycount": 20, "happiness": 80}, 1.0
            )
            # Blast deaths, then radiation fallout kills NUKE_FALLOUT_DEATHS of
            # the whole target nation (wars/aftermath.py, 2026-10-04 rebalance).
            from wars import aftermath
            survivors = 10_000_000 - expected["deaths"]
            assert pop == survivors - int(survivors * aftermath.NUKE_FALLOUT_DEATHS)
            assert cities == 20 - expected["cities_destroyed"]
            assert happy == 80 - nk.HAPPINESS_HIT
            assert working < 5_000_000
            db.execute(
                "SELECT ub.quantity FROM user_buildings ub JOIN building_dictionary bd "
                "ON bd.building_id = ub.building_id WHERE ub.province_id=%s AND bd.name='farms'",
                (b_prov,),
            )
            assert db.fetchone()[0] < 100
            db.execute(
                "SELECT influence_cost, is_retaliation, buildings_destroyed FROM nuclear_strikes "
                "WHERE attacker_id=%s", (a,),
            )
            cost, retal, bdest = db.fetchone()
            assert not retal and cost == infl_before // 2 and bdest > 0
            db.execute("SELECT count(*) FROM news WHERE destination_id IN (%s,%s) AND message LIKE '%%NUCLEAR%%' OR (destination_id=%s AND message LIKE '%%nuclear strike%%')", (a, b, a))
            assert db.fetchone()[0] >= 2
            db.execute(
                "SELECT quantity FROM user_military um JOIN unit_dictionary ud ON ud.unit_id=um.unit_id "
                "WHERE um.user_id=%s AND ud.name='nukes'", (a,),
            )
            assert db.fetchone()[0] == 2
            # influence dropped by the (barely decayed) penalty; the spent
            # nuke no longer counts against the stockpile (+25,000)
            after = nk.fresh_influence(db, a)
            assert after == pytest.approx(infl_before - cost + 25000, abs=50)

            # A is now under 1M -> a second first-strike is blocked
            assert after < 1_000_000
            plan = nk.plan_strike(db, a, war_id)
            assert plan["blocked"]

            # repeat decay: the struck province now previews at 50%
            _plan_b = nk.plan_strike(db, b, war_id)
            conn.rollback()

        # B retaliates despite being under 1M; costs 25%
        query_cache.invalidate(pattern="influence_")
        _login(client, b)
        r = client.get(f"/nuclear_strike/{war_id}")
        assert b"Retaliation" in r.data
        r, _ = _review_and_launch(client, war_id, a_prov)
        assert r.status_code == 200
        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute("SELECT is_retaliation, influence_cost, influence_before FROM nuclear_strikes WHERE attacker_id=%s", (b,))
            retal, cost_b, before_b = db.fetchone()
            assert retal and cost_b == before_b // 4

            # second hit on B's province within 72h -> halved damage preview
            db.execute(
                "INSERT INTO user_military (user_id, unit_id, quantity) SELECT %s, unit_id, 1 "
                "FROM unit_dictionary WHERE name='nukes' ON CONFLICT (user_id, unit_id) DO UPDATE SET quantity=1",
                (a,),
            )
            provs = nk.enemy_provinces(db, b)
            assert provs[0]["damage"]["multiplier"] == pytest.approx(0.5, abs=0.01)
            conn.rollback()

        # warChoose routes nukes to the planner
        _login(client, a)
        with client.session_transaction() as sess:
            sess["enemy_id"] = b  # set by the real attack flow
        r = client.post(f"/warchoose/{war_id}", data={"special_unit": "nukes"})
        assert r.status_code in (302, 303) and f"/nuclear_strike/{war_id}" in r.headers["Location"]
    finally:
        query_cache.invalidate(pattern="influence_")
        with get_db_connection() as conn:
            db = conn.cursor()
            for uid in ids:
                db.execute("DELETE FROM nuclear_strikes WHERE attacker_id=%s OR target_id=%s", (uid, uid))
                db.execute("DELETE FROM wars WHERE attacker=%s OR defender=%s", (uid, uid))
                db.execute("DELETE FROM news WHERE destination_id=%s", (uid,))
                db.execute("DELETE FROM user_buildings WHERE user_id=%s", (uid,))
                db.execute("DELETE FROM user_military WHERE user_id=%s", (uid,))
                db.execute("DELETE FROM provinces WHERE userid=%s", (uid,))
                db.execute("DELETE FROM referral_active_days WHERE referred_user_id=%s", (uid,))
                db.execute("DELETE FROM stats WHERE id=%s", (uid,))
                purge_users_where(db, 'id=%s', (uid,))
            try:
                db.execute("DELETE FROM world_events WHERE actor_id = ANY(%s)", (ids,))
            except Exception:
                conn.rollback()
            conn.commit()


@needs_db
def test_two_concurrent_launches_spend_one_nuke_once():
    """Two launches racing on separate connections with ONE nuke in stock:
    exactly one fires (advisory lock + "quantity > 0" decrement in
    execute_strike). Replaces the old /nuclear_strike double-spend test,
    which targeted the pre-rework one-shot route."""
    import threading
    from database import get_db_connection, query_cache

    ids = []
    try:
        with get_db_connection() as conn:
            db = conn.cursor()
            a, _, _ = _mk_user(db, "ra", 300_000_000)
            b, _, b_prov = _mk_user(db, "rb", 10_000_000)
            ids = [a, b]
            _give_nukes(db, a, 1)
            db.execute(
                "INSERT INTO wars (attacker, defender, war_type, agressor_message, start_date, last_visited) "
                "VALUES (%s, %s, 'Raze', 'test', extract(epoch from now()), extract(epoch from now())) RETURNING id",
                (a, b),
            )
            war_id = db.fetchone()[0]
            conn.commit()
        query_cache.invalidate(pattern="influence_")

        barrier = threading.Barrier(2)
        outcomes = []

        def _launch():
            with get_db_connection() as conn:
                db = conn.cursor()
                barrier.wait(timeout=5)
                try:
                    nk.execute_strike(db, a, war_id, b_prov)
                    conn.commit()
                    outcomes.append("fired")
                except nk.StrikeError as exc:
                    conn.rollback()
                    outcomes.append(f"refused: {exc}")

        threads = [threading.Thread(target=_launch) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert sorted(o == "fired" for o in outcomes) == [False, True], outcomes
        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute(
                "SELECT um.quantity FROM user_military um JOIN unit_dictionary ud "
                "ON ud.unit_id = um.unit_id WHERE ud.name = 'nukes' AND um.user_id = %s",
                (a,),
            )
            assert db.fetchone()[0] == 0
    finally:
        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute("DELETE FROM nuclear_strikes WHERE attacker_id = ANY(%s) OR target_id = ANY(%s)", (ids, ids))
            db.execute("DELETE FROM wars WHERE attacker = ANY(%s) OR defender = ANY(%s)", (ids, ids))
            purge_users_where(db, "id = ANY(%s)", (ids,))
            conn.commit()

