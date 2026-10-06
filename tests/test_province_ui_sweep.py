"""Province UI sweep (2026-09-27):

1. Mass Purchase of cities/land ("add N to each" / "bring each up to X"),
   priced exactly like single-province buys, all-or-nothing, one deduction.
2. Per-province population growth on the province page / provinces list.
3. Revenue history ledger (nation_revenue_history, migration 0087).
5. Pollution: reductions act on the raw uncapped total, clamp 0-100 last.
6. "Show my province info to other players" toggle.

Pure tests always run. DB tests need a THROWAWAY local Postgres (this
machine's shell can point at prod -- run with
`env -u DATABASE_PUBLIC_URL DATABASE_URL=postgresql://...localhost.../x`).
Every row the DB tests create is removed in `finally`.
"""

import os
import uuid

import pytest

import variables
from app_core.economy.building_costs import (
    LAND_CITY_PRICING,
    land_city_purchase_cost,
    sum_cost_capped_linear,
)
from app_core.economy.province_effects import (
    apply_effect,
    clamp_percentage,
    pop_cap_marginals,
    province_stat_breakdown,
)

PERCENTAGE_BASED = ("happiness", "productivity", "consumer_spending", "pollution")

_db_url = os.getenv("DATABASE_URL") or ""
needs_local_db = pytest.mark.skipif(
    not _db_url or ("localhost" not in _db_url and "127.0.0.1" not in _db_url),
    reason="Requires a throwaway local Postgres in DATABASE_URL",
)


# ---------------------------------------------------------------------------
# 1. Pricing (pure)
# ---------------------------------------------------------------------------


def _one_by_one(unit, current, n):
    base, inc, cap = LAND_CITY_PRICING[unit]
    return sum(min(base + (current + i) * inc, base + cap * inc) for i in range(n))


@pytest.mark.parametrize("unit", ["cityCount", "land"])
@pytest.mark.parametrize("current,n", [(0, 1), (5, 10), (95, 20), (199, 3), (300, 7)])
def test_land_city_cost_equals_buying_one_by_one(unit, current, n):
    assert land_city_purchase_cost(unit, current, n, []) == _one_by_one(unit, current, n)
    # And splitting a purchase in two costs the same as doing it at once.
    half = n // 2
    split = land_city_purchase_cost(unit, current, half, []) + land_city_purchase_cost(
        unit, current + half, n - half, []
    )
    assert split == land_city_purchase_cost(unit, current, n, [])


def test_land_city_cost_applies_policy_discount_like_single_route():
    raw = sum_cost_capped_linear(750000, 50000, 3, 4, 200)
    assert land_city_purchase_cost("cityCount", 3, 4, [2]) == int(raw * 0.96)
    assert land_city_purchase_cost("cityCount", 3, 0, [2]) == 0


# ---------------------------------------------------------------------------
# 5. Pollution clamp order (pure)
# ---------------------------------------------------------------------------


def _mine_pollution_per_unit():
    return variables.NEW_INFRA["coal_mines"]["eff"]["pollution"]


def _park_reduction_per_unit():
    return variables.NEW_INFRA["city_parks"]["effminus"]["pollution"]


def test_pollution_reductions_hit_raw_total_not_clamped_100():
    """200 mines push pollution far past 100; one park must not drop the
    province to ~94 as if the overflow never existed (Kurai/ieb report)."""
    mines = _mine_pollution_per_unit() * 200
    park = _park_reduction_per_unit()
    assert mines - park > 100  # the scenario is actually past the cap

    value = apply_effect(0, "pollution", mines, "+", PERCENTAGE_BASED)
    assert value == mines  # not clamped mid-pass
    value = apply_effect(value, "pollution", park, "-", PERCENTAGE_BASED)
    assert clamp_percentage(value) == 100

    # The old per-step clamp is what produced the bug:
    old = min(100, mines)
    old = max(0, old - park)
    assert old < 100


def test_pollution_clamps_to_zero_at_the_end():
    value = apply_effect(10, "pollution", 50, "-", PERCENTAGE_BASED)
    assert value == -40
    assert clamp_percentage(value) == 0


def test_other_stats_keep_per_step_clamp():
    assert apply_effect(95, "happiness", 20, "+", PERCENTAGE_BASED) == 100
    assert apply_effect(5, "productivity", 20, "-", PERCENTAGE_BASED) == 0


def test_breakdown_projection_uses_raw_pollution():
    units = {"coal_mines": 200, "city_parks": 1}
    b = province_stat_breakdown(
        {"happiness": 50, "pollution": 0, "productivity": 50}, units, {}, []
    )
    pol = b["pollution"]
    names = {s["name"] for s in pol["sources"]}
    assert {"coal_mines", "city_parks"} <= names
    assert pol["net"] == _mine_pollution_per_unit() * 200 - _park_reduction_per_unit()
    assert pol["projected"] == 100


def test_breakdown_lists_policy_happiness():
    b = province_stat_breakdown(
        {"happiness": 50, "pollution": 0, "productivity": 50},
        {},
        {},
        [variables.POLICY_UNIVERSAL_HEALTHCARE],
    )
    labels = [s.get("label") for s in b["happiness"]["sources"]]
    assert "Universal Healthcare policy" in labels
    assert b["happiness"]["projected"] == 50 + variables.POLICY_HEALTHCARE_HAPPINESS_BONUS


def test_pop_cap_marginals_diminish():
    a = pop_cap_marginals(0, 0)
    b = pop_cap_marginals(100, 300)
    assert a["city_next"] > b["city_next"] > 0
    assert a["land_next"] > b["land_next"] > 0
    assert a["city_soft"] == variables.CITY_POP_SOFTNESS
    assert a["land_tax_max"] == 51


# ---------------------------------------------------------------------------
# DB-backed tests
# ---------------------------------------------------------------------------


def _create_user(db, gold, provinces):
    name = f"provui_{uuid.uuid4().hex[:8]}"
    db.execute(
        "INSERT INTO users (username, email, date, hash, auth_type) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (name, f"{name}@example.test", "2026-09-27", "", "normal"),
    )
    uid = db.fetchone()[0]
    db.execute(
        "INSERT INTO stats (id, location, gold) VALUES (%s, %s, %s) "
        "ON CONFLICT (id) DO UPDATE SET gold = %s",
        (uid, "Grassland", gold, gold),
    )
    pids = []
    for i, (cities, land, pop) in enumerate(provinces):
        db.execute(
            "INSERT INTO provinces (userId, provinceName, cityCount, land, population, "
            "happiness, pollution, productivity) "
            "VALUES (%s, %s, %s, %s, %s, 50, 0, 50) RETURNING id",
            (uid, f"P{i}", cities, land, pop),
        )
        pids.append(db.fetchone()[0])
    return uid, pids


def _cleanup(uid):
    from database import get_db_connection

    with get_db_connection() as conn:
        db = conn.cursor()
        for sql in (
            "DELETE FROM purchase_audit WHERE user_id=%s",
            "DELETE FROM revenue WHERE user_id=%s",
            "DELETE FROM nation_revenue_history WHERE user_id=%s",
            "DELETE FROM user_buildings WHERE user_id=%s",
            "DELETE FROM referral_active_days WHERE referred_user_id=%s",
            "DELETE FROM provinces WHERE userId=%s",
            "DELETE FROM stats WHERE id=%s",
            "DELETE FROM users WHERE id=%s",
        ):
            db.execute(sql, (uid,))
        conn.commit()


@pytest.fixture
def client():
    from app import app

    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    return app.test_client()


def _login(client, uid):
    with client.session_transaction() as sess:
        sess["user_id"] = uid


def _state(uid, pids):
    from database import get_db_connection

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT gold FROM stats WHERE id=%s", (uid,))
        gold = db.fetchone()[0]
        db.execute(
            "SELECT id, CAST(cityCount AS INTEGER), land FROM provinces "
            "WHERE id = ANY(%s) ORDER BY id",
            (pids,),
        )
        rows = {r[0]: (r[1], r[2]) for r in db.fetchall()}
    return gold, rows


@needs_local_db
def test_mass_purchase_cities_add_and_target(client):
    from database import get_db_connection

    with get_db_connection() as conn:
        db = conn.cursor()
        uid, pids = _create_user(db, 200_000_000, [(2, 5, 1000), (10, 5, 1000)])
        conn.commit()
    try:
        _login(client, uid)
        expected = land_city_purchase_cost("cityCount", 2, 3, []) + land_city_purchase_cost(
            "cityCount", 10, 3, []
        )
        r = client.post(
            "/mass_purchase/preview",
            json={"building": "cityCount", "purchase_type": "add", "quantity": 3,
                  "province_ids": pids},
        )
        assert r.status_code == 200, r.get_data(as_text=True)
        assert r.get_json()["total_cost"] == expected
        assert r.get_json()["total_units"] == 6

        r = client.post(
            "/mass_purchase/buy",
            data={"building": "cityCount", "purchase_type": "add", "quantity": "3",
                  "province_ids": [str(p) for p in pids]},
        )
        assert r.status_code in (302, 303)
        gold, rows = _state(uid, pids)
        assert gold == 200_000_000 - expected
        assert rows[pids[0]][0] == 5 and rows[pids[1]][0] == 13

        # "Bring each up to 8": only the first province (5 cities) buys 3.
        expected2 = land_city_purchase_cost("cityCount", 5, 3, [])
        r = client.post(
            "/mass_purchase/buy",
            data={"building": "citycount", "purchase_type": "target", "quantity": "8",
                  "province_ids": [str(p) for p in pids]},
        )
        gold2, rows = _state(uid, pids)
        assert gold2 == gold - expected2
        assert rows[pids[0]][0] == 8 and rows[pids[1]][0] == 13
    finally:
        _cleanup(uid)


@needs_local_db
def test_mass_purchase_land_is_all_or_nothing(client):
    from database import get_db_connection

    cost_one = land_city_purchase_cost("land", 5, 4, [])
    with get_db_connection() as conn:
        db = conn.cursor()
        # Enough for one province's land, not both.
        uid, pids = _create_user(db, cost_one + 1000, [(1, 5, 1000), (1, 5, 1000)])
        conn.commit()
    try:
        _login(client, uid)
        r = client.post(
            "/mass_purchase/buy",
            data={"building": "land", "purchase_type": "add", "quantity": "4",
                  "province_ids": [str(p) for p in pids]},
        )
        assert r.status_code in (302, 303)
        gold, rows = _state(uid, pids)
        assert gold == cost_one + 1000
        assert all(v[1] == 5 for v in rows.values())
    finally:
        _cleanup(uid)


@needs_local_db
def test_mass_purchase_ignores_other_players_provinces(client):
    from database import get_db_connection

    with get_db_connection() as conn:
        db = conn.cursor()
        uid, pids = _create_user(db, 100_000_000, [(1, 1, 1000)])
        other, other_pids = _create_user(db, 0, [(1, 1, 1000)])
        conn.commit()
    try:
        _login(client, uid)
        client.post(
            "/mass_purchase/buy",
            data={"building": "land", "purchase_type": "add", "quantity": "2",
                  "province_ids": [str(pids[0]), str(other_pids[0])]},
        )
        _, rows = _state(uid, pids + other_pids)
        assert rows[pids[0]][1] == 3
        assert rows[other_pids[0]][1] == 1
    finally:
        _cleanup(uid)
        _cleanup(other)


@needs_local_db
def test_growth_rate_matches_nation_projection():
    from database import get_db_connection, query_cache
    from app_core.game_ticks.population import get_population_growth

    with get_db_connection() as conn:
        db = conn.cursor()
        uid, pids = _create_user(db, 0, [(5, 10, 500_000), (1, 1, 2_000_000)])
        conn.commit()
    try:
        query_cache.invalidate(f"pop_growth_{uid}")
        g = get_population_growth(uid)
        per = g["per_province"]
        assert set(per) == {str(p) for p in pids}
        assert sum(per.values()) == g["delta"]
    finally:
        _cleanup(uid)


@needs_local_db
def test_revenue_ledger_single_insert_and_totals():
    from database import get_db_connection
    from app_core.game_ticks.revenue_history import get_ledger_totals, record_gold_ledger

    with get_db_connection() as conn:
        db = conn.cursor()
        uid, _ = _create_user(db, 0, [])
        conn.commit()
    try:
        with get_db_connection() as conn:
            db = conn.cursor()
            n = record_gold_ledger(
                db,
                [(uid, "tax", 1000), (uid, "coalition_tax", -100),
                 (uid, "building_upkeep", -300), (uid, "tax", 0)],
                prune=True,
            )
            assert n == 3
            # An old row (outside 30 days) is pruned on the next prune.
            db.execute(
                "INSERT INTO nation_revenue_history (user_id, recorded_at, category, amount) "
                "VALUES (%s, NOW() - INTERVAL '40 days', 'tax', 5)",
                (uid,),
            )
            record_gold_ledger(db, [(uid, "tax", 500)], prune=True)
            conn.commit()
            totals = get_ledger_totals(db, uid)
        rows = {r["label"]: r for r in totals["rows"]}
        assert rows["Taxes"]["24h"] == 1500
        assert rows["Coalition tax"]["30d"] == 100
        assert rows["Building upkeep"]["kind"] == "spending"
        assert totals["net"]["7d"] == 1500 - 100 - 300
        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute(
                "SELECT COUNT(*) FROM nation_revenue_history WHERE user_id=%s "
                "AND recorded_at < NOW() - INTERVAL '30 days'",
                (uid,),
            )
            assert db.fetchone()[0] == 0
    finally:
        _cleanup(uid)


@needs_local_db
def test_revenue_ledger_failure_does_not_break_transaction():
    from database import get_db_connection
    from app_core.game_ticks.revenue_history import record_gold_ledger

    with get_db_connection() as conn:
        db = conn.cursor()
        uid, _ = _create_user(db, 777, [])
        conn.commit()
    try:
        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute("UPDATE stats SET gold = 999 WHERE id=%s", (uid,))
            # category too long for VARCHAR(32) -> the INSERT fails
            assert record_gold_ledger(db, [(uid, "x" * 64, 5)]) == 0
            db.execute("SELECT gold FROM stats WHERE id=%s", (uid,))
            assert db.fetchone()[0] == 999  # txn still usable, earlier work kept
            conn.commit()
    finally:
        _cleanup(uid)


@needs_local_db
def test_public_province_info_toggle(client):
    from database import get_db_connection

    with get_db_connection() as conn:
        db = conn.cursor()
        uid, _ = _create_user(db, 0, [])
        other, _ = _create_user(db, 0, [])
        conn.commit()
    try:
        _login(client, uid)
        r = client.post(
            "/update_country_info",
            data={"description": "None", "public_province_info_present": "1",
                  "public_province_info": "1", "countryLocation": ""},
        )
        assert r.status_code in (302, 303), r.get_data(as_text=True)[:500]

        def flag(u):
            with get_db_connection() as conn:
                db = conn.cursor()
                db.execute("SELECT public_province_info FROM users WHERE id=%s", (u,))
                return db.fetchone()[0]

        assert flag(uid) is True
        assert flag(other) is False
        # Unchecked box + marker -> off. A form without the marker leaves it alone.
        client.post("/update_country_info",
                    data={"description": "None", "countryLocation": ""})
        assert flag(uid) is True
        client.post("/update_country_info",
                    data={"description": "None", "public_province_info_present": "1",
                          "countryLocation": ""})
        assert flag(uid) is False
    finally:
        _cleanup(uid)
        _cleanup(other)


@needs_local_db
def test_real_ticks_write_ledger_and_clamp_pollution_last():
    """Run the real hourly revenue + tax ticks: 200 coal mines + 1 park keep
    pollution at 100 (not ~94), and the ledger rows add up to the actual gold
    change. Processes every nation in the (throwaway) DB."""
    from database import get_db_connection
    from app_core.game_ticks.revenue import generate_province_revenue
    from app_core.game_ticks.taxes import tax_income

    start_gold = 10**12
    with get_db_connection() as conn:
        db = conn.cursor()
        uid, pids = _create_user(db, start_gold, [(50, 400, 2_000_000)])
        db.execute("UPDATE provinces SET pollution = 90 WHERE id=%s", (pids[0],))
        for name, q in (("coal_mines", 200), ("city_parks", 1)):
            db.execute(
                "INSERT INTO user_buildings (user_id, building_id, province_id, quantity) "
                "SELECT %s, building_id, %s, %s FROM building_dictionary WHERE name=%s",
                (uid, pids[0], q, name),
            )
        db.execute(
            "UPDATE task_runs SET last_run = now() - interval '1 day', last_period = NULL "
            "WHERE task_name IN ('generate_province_revenue', 'tax_income')"
        )
        conn.commit()
    try:
        generate_province_revenue()
        tax_income()
        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute("SELECT pollution FROM provinces WHERE id=%s", (pids[0],))
            assert db.fetchone()[0] == 100
            db.execute(
                "SELECT category, SUM(amount) FROM nation_revenue_history "
                "WHERE user_id=%s GROUP BY category",
                (uid,),
            )
            ledger = dict(db.fetchall())
            db.execute("SELECT gold FROM stats WHERE id=%s", (uid,))
            gold_delta = db.fetchone()[0] - start_gold
        assert ledger.get("building_upkeep", 0) < 0
        assert ledger.get("tax", 0) > 0
        assert sum(ledger.values()) == gold_delta
    finally:
        _cleanup(uid)
