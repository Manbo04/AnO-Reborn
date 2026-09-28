"""Influence blend (2026-09-27): pure-formula checks + SQL/Python parity.

The DB test creates two throwaway users and removes them in `finally`. Run
against a local Postgres only:
    env -u DATABASE_PUBLIC_URL DATABASE_URL=postgresql://...local... pytest
"""

import os
import uuid

import pytest

import influence_formula as inf


def test_military_ordering_matches_spec():
    order = [
        "aircraft_carriers", "cruisers", "destroyers", "submarines", "bombers",
        "fighters", "apaches", "tanks", "artillery", "soldiers",
    ]
    weights = [inf.UNIT_WEIGHTS[u] for u in order]
    assert weights == sorted(weights, reverse=True)
    assert len(set(weights)) == len(weights)


def test_missiles_subtract_in_spec_order():
    order = ["nukes", "icbms", "kamikaze_drones", "cruise_missiles"]
    pens = [inf.MISSILE_PENALTIES[m] for m in order]
    assert pens == sorted(pens, reverse=True) and min(pens) > 0
    base = {"population": 10_000_000}
    with_nuke = {**base, "units": {"nukes": 1}}
    assert inf.compute_influence(with_nuke) == inf.compute_influence(base) - 25000


def test_resource_values_and_60_40_split():
    assert inf.RESOURCE_VALUE_PER_KG["components"] == 155298
    assert inf.RESOURCE_VALUE_PER_KG["lumber"] == 87
    # one farm = 100 rations/h (variables.NEW_INFRA) -> 100 * 244
    assert inf.BUILDING_HOURLY_VALUE["farms"] == 100 * 244
    stock_only = inf.compute_influence({"stockpile": {"steel": 1_000_000}})
    assert stock_only == round(inf.RESOURCE_SCALE * 0.4 * 9244 * 1_000_000)
    prod_only = inf.compute_influence({"building_counts": {"farms": 1000}})
    assert prod_only == round(inf.RESOURCE_SCALE * 0.6 * 24400 * 1000)


def test_gold_counts_inside_stockpile_share_and_floor_zero():
    gold = 1_000_000_000
    expected = round(inf.RESOURCE_SCALE * inf.STOCKPILE_SHARE * inf.GOLD_STOCKPILE_VALUE * gold)
    assert inf.compute_influence({"gold": gold}) == expected
    # far below the old 1 point per $100k
    assert expected < gold / 100_000
    assert inf.compute_influence({"units": {"nukes": 5}}) == 0


def test_nuclear_penalty_decays_linearly_over_7_days():
    assert inf.nuclear_penalty_remaining(1000, 0) == 1000
    assert inf.nuclear_penalty_remaining(1000, 3.5 * 86400) == pytest.approx(500)
    assert inf.nuclear_penalty_remaining(1000, 8 * 86400) == 0


def test_sql_uses_plain_decimals():
    sql = inf.influence_subquery_sql("SELECT 1")
    assert "e-0" not in sql and "%" not in sql.replace("%s", "")


pytestmark_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL") or os.getenv("DATABASE_PUBLIC_URL"),
    reason="Needs a LOCAL Postgres in DATABASE_URL (and no DATABASE_PUBLIC_URL)",
)


@pytestmark_db
def test_sql_matches_python_and_callers():
    from database import get_db_connection, query_cache
    from helpers import get_bulk_influence, get_influence

    uids = []
    try:
        with get_db_connection() as conn:
            db = conn.cursor()
            for i in range(2):
                name = f"inftest_{uuid.uuid4().hex[:8]}"
                db.execute(
                    "INSERT INTO users (username, email, date, hash, auth_type) "
                    "VALUES (%s, %s, '2026-09-27', '', 'normal') RETURNING id",
                    (name, f"{name}@example.test"),
                )
                uids.append(db.fetchone()[0])
                db.execute(
                    "INSERT INTO stats (id, location, gold) VALUES (%s, 'Grassland', 999999999)",
                    (uids[-1],),
                )
            a = uids[0]
            db.execute(
                "INSERT INTO provinces (userid, provincename, citycount, land, population) "
                "VALUES (%s, 'P1', 20, 50, 12345678), (%s, 'P2', 3, 7, 1000000) RETURNING id",
                (a, a),
            )
            p1 = db.fetchone()[0]
            units = {"soldiers": 5000, "tanks": 40, "aircraft_carriers": 2, "nukes": 1, "cruise_missiles": 3}
            for u, q in units.items():
                db.execute(
                    "INSERT INTO user_military (user_id, unit_id, quantity) "
                    "SELECT %s, unit_id, %s FROM unit_dictionary WHERE name = %s",
                    (a, q, u),
                )
            stock = {"steel": 20000, "components": 1500, "lumber": 90000}
            for r, q in stock.items():
                db.execute(
                    "INSERT INTO user_economy (user_id, resource_id, quantity) "
                    "SELECT %s, resource_id, %s FROM resource_dictionary WHERE name = %s "
                    "ON CONFLICT (user_id, resource_id) DO UPDATE SET quantity = EXCLUDED.quantity",
                    (a, q, r),
                )
            blds = {"farms": 12, "steel_mills": 3, "hospitals": 2}
            for b, q in blds.items():
                db.execute(
                    "INSERT INTO user_buildings (user_id, building_id, province_id, quantity) "
                    "SELECT %s, building_id, %s, %s FROM building_dictionary WHERE name = %s",
                    (a, p1, q, b),
                )
            # a strike launched 1 day ago with a 70,000 cost
            db.execute(
                "INSERT INTO nuclear_strikes (attacker_id, target_id, province_id, launched_at, "
                "recovers_at, influence_cost) VALUES (%s, %s, %s, now() - interval '1 day', "
                "now() + interval '6 days', 70000)",
                (a, uids[1], p1),
            )
            conn.commit()

        expected = inf.compute_influence(
            {
                "population": 12345678 + 1000000,
                "provinces": 2,
                "cities": 23,
                "land": 57,
                "buildings": 17,
                "units": units,
                "stockpile": stock,
                "building_counts": blds,
                "gold": 999999999,
                "nuclear_penalty": inf.nuclear_penalty_remaining(70000, 86400),
            }
        )
        query_cache.invalidate(pattern="influence_")
        got = get_influence(a)
        assert abs(got - expected) <= 1, (got, expected)
        query_cache.invalidate(pattern="influence_")
        from app import app

        with app.test_request_context():
            bulk = get_bulk_influence(uids)
        assert abs(bulk[a] - expected) <= 1
        # second user owns only gold: it counts inside the stockpile share
        assert abs(bulk[uids[1]] - inf.compute_influence({"gold": 999999999})) <= 1
    finally:
        query_cache.invalidate(pattern="influence_")
        with get_db_connection() as conn:
            db = conn.cursor()
            for uid in uids:
                db.execute("DELETE FROM nuclear_strikes WHERE attacker_id = %s OR target_id = %s", (uid, uid))
                db.execute("DELETE FROM user_buildings WHERE user_id = %s", (uid,))
                db.execute("DELETE FROM user_economy WHERE user_id = %s", (uid,))
                db.execute("DELETE FROM user_military WHERE user_id = %s", (uid,))
                db.execute("DELETE FROM provinces WHERE userid = %s", (uid,))
                db.execute("DELETE FROM stats WHERE id = %s", (uid,))
                db.execute("DELETE FROM users WHERE id = %s", (uid,))
            conn.commit()
