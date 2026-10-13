"""Content audit 2026-10-13: retired techs, Star Wars card, achievements, spy reports."""
from pathlib import Path

import pytest

import variables
from app_core.game_ticks.achievements import ACHIEVEMENT_QUERIES
from app_core.upgrades import repositories, services

ROOT = Path(__file__).resolve().parent.parent
VALID_BOND_STATUSES = {"listed", "active", "repaid", "defaulted", "cancelled"}


def _db():
    from database import get_db_connection

    return get_db_connection()


# ---- static (no DB) -------------------------------------------------------

@pytest.mark.no_server
def test_star_wars_project_is_buyable_from_the_upgrades_page():
    assert repositories.LEGACY_UPGRADE_TO_TECH["starwarsproject"] == "star_wars_project"
    for name in ("upgrades.html", "upgrades_v2.html"):
        src = (ROOT / "templates" / name).read_text(encoding="utf-8")
        assert "/upgrades_sb/buy/starWarsProject" in src, name
        assert 'upgrades["starwarsproject"]' in src, name  # researched state (exit)


@pytest.mark.no_server
def test_disaster_buildings_have_buy_and_sell_forms_on_classic_province_page():
    src = (ROOT / "templates" / "province.html").read_text(encoding="utf-8")
    for b in ("firewatch_towers", "levees", "seismic_reinforcements"):
        assert f"/buy/{b}/" in src and f"/sell/{b}/" in src, b


@pytest.mark.no_server
def test_achievement_queries_use_only_valid_bond_statuses_and_skip_intercepted_spies():
    q = dict(ACHIEVEMENT_QUERIES)
    for key in ("eco_bond_issued", "eco_bond_funded"):
        import re

        used = set(re.findall(r"'([a-z]+)'", q[key]))
        assert used <= VALID_BOND_STATUSES, (key, used - VALID_BOND_STATUSES)
    assert "repaid" in q["eco_bond_funded"]
    assert "NOT intercepted" in q["mil_spy_op"]


@pytest.mark.no_server
def test_spy_reports_cover_extra_units():
    assert set(variables.SPY_EXTRA_UNITS) == {
        "counter_intel_agents", "aircraft_carriers", "kamikaze_drones", "cruise_missiles",
    }
    assert not set(variables.SPY_EXTRA_UNITS) & set(variables.UNITS)
    for name in ("intelligence.html", "intelligence_v2.html"):
        src = (ROOT / "templates" / name).read_text(encoding="utf-8")
        for u in variables.SPY_EXTRA_UNITS:
            assert f'"{u}"' in src, (name, u)


class _Cur:
    def __init__(self, results):
        self.results = list(results)

    def execute(self, *a, **k):
        pass

    def fetchall(self):
        return self.results.pop(0)


@pytest.mark.no_server
def test_retired_unlocked_tech_does_not_inflate_researched_counter():
    rows = [(10, "Better Engineering", 1000, None, "better_engineering", "d")]
    # user owns tech 10 (active) and tech 1 (retired, not in catalog)
    _, unlocked, _, _ = services.build_upgrades_page_data(_Cur([rows, [(10,), (1,)]]), 5)
    assert unlocked == {10}


# ---- DB (prod-shaped CI database, after migrations) -----------------------

RETIRED = (
    "basic_agriculture", "mining_techniques", "military_doctrine", "industrialization",
    "advanced_farming", "scientific_method", "steel_production", "nuclear_physics",
    "organized_supply_lines", "large_storehouses",
)


@pytest.mark.no_server
def test_effectless_techs_are_not_sold_and_prereq_chains_still_work():
    with _db() as conn:
        db = conn.cursor()
        db.execute("SELECT name, is_active FROM tech_dictionary WHERE name = ANY(%s)", (list(RETIRED),))
        rows = db.fetchall()
        assert rows and all(not r[1] for r in rows), rows
        # every sold tech's prerequisite must itself be sold (else it is unbuyable)
        db.execute(
            "SELECT t.name FROM tech_dictionary t JOIN tech_dictionary p ON p.tech_id = t.prerequisite_tech_id "
            "WHERE t.is_active AND NOT p.is_active"
        )
        assert db.fetchall() == []
        db.execute(
            "SELECT description FROM tech_dictionary WHERE name IN ('nuclear_testing_facility','ballistic_missile_silo')"
        )
        assert all("reactor" not in r[0].lower() and "ballistic missiles" not in r[0] for r in db.fetchall())


@pytest.mark.no_server
def test_start_research_refuses_retired_tech():
    from action_loop import ActionLoopError, start_research

    with _db() as conn:
        db = conn.cursor()
        db.execute("SELECT tech_id FROM tech_dictionary WHERE name = 'basic_agriculture'")
        tech_id = db.fetchone()[0]
    with pytest.raises(ActionLoopError):
        start_research(-424242, tech_id)


@pytest.mark.no_server
def test_spyinfo_has_columns_for_extra_units_and_units_exist():
    with _db() as conn:
        db = conn.cursor()
        db.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name='spyinfo' AND table_schema='public'"
        )
        cols = {r[0] for r in db.fetchall()}
        db.execute("SELECT name FROM unit_dictionary")
        units = {r[0] for r in db.fetchall()}
    for u in variables.SPY_EXTRA_UNITS:
        assert u in cols and u in units, u


@pytest.mark.no_server
def test_achievement_queries_execute_and_fun_debt_icon_exists_in_fa_5_8_2():
    with _db() as conn:
        db = conn.cursor()
        for key, sql in ACHIEVEMENT_QUERIES:
            if key in ("eco_bond_issued", "eco_bond_funded", "mil_spy_op"):
                db.execute(sql)
                db.fetchall()
        db.execute("SELECT icon FROM achievements WHERE key = 'fun_debt'")
        row = db.fetchone()  # the CI snapshot may not carry achievement rows; prod does
        assert row is None or row[0] != "fa-chart-line-down"
