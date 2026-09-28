"""ieb's "turn change" report + Kurai's steel numbers (2026-09-27).

- tick_order: between the :25 upkeep tick and the :00 tax payout the
  projections count the coming tax income, so a nation that just spent its
  gold no longer shows every net at 0 / provinces unpowered.
- project_bonuses: national-project output bonuses are additive with
  productivity (same numbers in tick, projection and province page).
- The province page shows the real per-building output the tick pays.
"""
import datetime as dt
import re
import uuid

import bcrypt
import pytest

from app_core.economy.project_bonuses import project_output_bonus
from app_core.economy.tick_order import tax_due_before_next_upkeep, upkeep_budget


def _at(minute):
    return dt.datetime(2026, 9, 22, 10, minute, tzinfo=dt.timezone.utc)


@pytest.mark.parametrize(
    "minute,expected",
    [(0, False), (10, False), (24, False), (25, True), (30, True), (59, True)],
)
def test_tax_due_before_next_upkeep(minute, expected):
    assert tax_due_before_next_upkeep(_at(minute), 0, 25) is expected


def test_default_schedule_minutes_are_read_from_beat_config():
    # Defaults: tax :00, upkeep :25.
    assert tax_due_before_next_upkeep(_at(40)) is True
    assert tax_due_before_next_upkeep(_at(5)) is False


def test_upkeep_budget():
    assert upkeep_budget(527, 1_000_000, _at(40)) == 1_000_527
    assert upkeep_budget(527, 1_000_000, _at(10)) == 527
    assert upkeep_budget(527, -50, _at(40)) == 527


def test_project_output_bonus():
    assert project_output_bonus("steel_mills", {"integratedsteelmaking": True}) == 0.36
    assert project_output_bonus("steel_mills", {}) == 0.0
    assert project_output_bonus("farms", {"advancedmachinery": True}) == 0.5
    assert project_output_bonus("bauxite_mines", {"strongerexplosives": True}) == 0.45
    assert project_output_bonus("iron_mines", {"integratedsteelmaking": True}) == 0.0


# ---------------------------------------------------------------- real DB --

PW = bcrypt.hashpw(b"x-test-pw", bcrypt.gensalt()).decode()


@pytest.fixture
def steel_nation():
    from database import get_db_connection

    with get_db_connection() as conn:
        db = conn.cursor()
        name = f"steeltest_{uuid.uuid4().hex[:10]}"
        db.execute(
            "INSERT INTO users (username, email, date, hash, auth_type) "
            "VALUES (%s, %s, '2026-09-27', %s, 'normal') RETURNING id",
            (name, f"{name}@example.com", PW),
        )
        uid = db.fetchone()[0]
        db.execute(
            "INSERT INTO stats (id, location, gold) VALUES (%s, 'Tundra', 0)", (uid,)
        )
        db.execute(
            "INSERT INTO provinces (userid, provincename, land, citycount, population, "
            "productivity, pop_working, pop_children, pop_elderly, edu_none, energy) "
            "VALUES (%s, 'Forge', 100, 10, 2000000, 100, 2000000, 0, 0, 50000000, 0) "
            "RETURNING id",
            (uid,),
        )
        pid = db.fetchone()[0]
        for bname, qty in (("steel_mills", 10), ("wind_farms", 10)):
            db.execute(
                "INSERT INTO user_buildings (user_id, building_id, quantity, province_id) "
                "SELECT %s, building_id, %s, %s FROM building_dictionary WHERE name=%s",
                (uid, qty, pid, bname),
            )
        db.execute(
            "INSERT INTO user_tech (user_id, tech_id, is_unlocked) "
            "SELECT %s, tech_id, TRUE FROM tech_dictionary WHERE name='integrated_steelmaking'",
            (uid,),
        )
        conn.commit()
    yield uid, pid
    with get_db_connection() as conn:
        db = conn.cursor()
        for sql in (
            "DELETE FROM user_tech WHERE user_id=%s",
            "DELETE FROM user_buildings WHERE user_id=%s",
            "DELETE FROM user_economy WHERE user_id=%s",
            "DELETE FROM provinces WHERE userid=%s",
            "DELETE FROM policies WHERE user_id=%s",
            "DELETE FROM news WHERE destination_id=%s",
            "DELETE FROM referral_active_days WHERE referred_user_id=%s",
            "DELETE FROM stats WHERE id=%s",
            "DELETE FROM users WHERE id=%s",
        ):
            try:
                db.execute(sql, (uid,))
            except Exception:
                conn.rollback()
        conn.commit()


def _revenue(uid):
    import countries
    from database import query_cache

    query_cache.invalidate(f"revenue_{uid}")
    return countries.get_revenue(uid)


def test_projection_counts_tax_after_upkeep_tick(steel_nation, monkeypatch):
    import app_core.economy.tick_order as tick_order

    uid, _ = steel_nation

    monkeypatch.setattr(tick_order, "tax_due_before_next_upkeep", lambda now=None: False)
    before_tax = _revenue(uid)
    monkeypatch.setattr(tick_order, "tax_due_before_next_upkeep", lambda now=None: True)
    after_upkeep = _revenue(uid)

    tax = after_upkeep["next_tax_income"]
    upkeep = 10 * 60000 + 10 * 8000
    assert tax > upkeep, "fixture must earn enough tax to cover upkeep"
    # $0 treasury, :00-:25 window: nothing can run (same as the real tick).
    assert before_tax["net"]["steel"] == 0
    # :25-:00 window: the tax lands first, so the mills will run.
    assert after_upkeep["net"]["steel"] > 0
    assert after_upkeep["net"]["steel"] == after_upkeep["gross"]["steel"]


def test_projection_steel_matches_tick_formula(steel_nation, monkeypatch):
    import math

    import variables
    import app_core.economy.tick_order as tick_order
    from app_core.economy.industry_bonuses import production_bonuses

    uid, _ = steel_nation
    monkeypatch.setattr(tick_order, "tax_due_before_next_upkeep", lambda now=None: True)
    rev = _revenue(uid)
    counts = {"steel_mills": 10, "wind_farms": 10}
    bonus = production_bonuses("steel_mills", counts, 100, 10, counts)["multiplier"]
    base = variables.NEW_INFRA["steel_mills"]["plus"]["steel"]
    # productivity 100 -> x1.45, +0.36 additive, workforce 1.0
    expected = math.ceil(10 * base * (1.45 + 0.36) * bonus)
    assert rev["gross"]["steel"] == expected


def test_province_page_shows_real_per_mill_output(steel_nation):
    import variables
    from app import app
    from app_core.economy.industry_bonuses import production_bonuses

    uid, pid = steel_nation
    app.config["TESTING"] = True
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = uid
    r = client.get(f"/province/{pid}")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    counts = {"steel_mills": 10, "wind_farms": 10}
    bonus = production_bonuses("steel_mills", counts, 100, 10, counts)["multiplier"]
    per_mill = round(variables.NEW_INFRA["steel_mills"]["plus"]["steel"] * 1.81 * bonus, 1)
    m = re.findall(r"Actual output here right now: ([0-9.,]+) kg steel per building", html)
    assert m, "per-mill actual output line missing"
    assert float(m[0].replace(",", "")) == pytest.approx(per_mill, abs=0.01)
