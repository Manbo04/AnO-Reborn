import pytest
import variables

pytestmark = pytest.mark.no_server


def test_malls_upkeep_rebalanced():
    """Verify retail malls upkeep was rebalanced from $150,000 to $60,000 (ratio $2,000 / CG)."""
    assert variables.INFRA["malls_money"] == 60_000
    assert variables.NEW_INFRA["malls"]["money"] == 60_000
    cg = variables.NEW_INFRA["malls"]["plus"]["consumer_goods"]
    assert cg == 30
    assert variables.NEW_INFRA["malls"]["money"] / cg == 2000.0


def test_workforce_efficiency_multiplier_clamped(monkeypatch):
    """Verify efficiency multiplier is strictly clamped between PRODUCTION_EFFICIENCY_MIN and 1.0."""
    import app_core.game_ticks.population as pop_module

    # Mock workforce availability and buildings/demographics
    monkeypatch.setattr(variables, "FEATURE_PHASE3_WORKFORCE", True)

    class DummyCursor:
        def __init__(self, working, elderly, buildings):
            self.working = working
            self.elderly = elderly
            self.buildings = buildings
            self.query = ""

        def execute(self, query, params=None):
            self.query = query

        def fetchone(self):
            return (self.working, self.elderly)

        def fetchall(self):
            return self.buildings

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    # Case 1: Huge surplus workforce (1,000,000 workers vs 500 jobs needed).
    # Must NOT produce huge multiplier; must be clamped to 1.0.
    monkeypatch.setattr(
        pop_module,
        "calculate_workforce_available",
        lambda uid: {"total": 1_000_000, "by_education": {"none": 1_000_000}},
    )
    # 1 building needing 500 jobs: (building_name, quantity)
    dummy_db = DummyCursor(1_000_000, 100_000, [("steel_mills", 1)])
    monkeypatch.setattr("database.get_db_cursor", lambda: dummy_db)

    res_surplus = pop_module.apply_workforce_hiring_and_debuffs(user_id=1)
    assert res_surplus["efficiency_multiplier"] == 1.0


def test_country_repository_strength_excludes_military():
    """Verify CountryRepository calculates strength purely from population (matching wars.war_range)."""
    import inspect
    from repositories.country_repository import CountryRepository

    source = inspect.getsource(CountryRepository.get_countries_paginated)
    # Must use population / 1000.0
    assert "(COALESCE(p.province_population, 0) / 1000.0) AS strength" in source
    # Must NOT include user_military in strength calculation
    assert "COALESCE(mil.mil_strength, 0)" not in source
    assert "user_military" not in source


def test_coalition_bank_redirects_retain_bank_tab():
    """Verify all coalition bank actions redirect back to the bank tab (#bank)."""
    import inspect
    import app_core.coalitions.routes as col_routes

    bank_handlers = [
        col_routes.deposit_into_bank,
        col_routes.withdraw,
        col_routes.withdraw_from_bank,
        col_routes.withdraw_personal_from_bank,
        col_routes.adjust_personal_bank,
        col_routes.request_from_bank,
        col_routes.remove_bank_request,
        col_routes.accept_bank_request,
    ]

    for handler in bank_handlers:
        src = inspect.getsource(handler)
        for line in src.splitlines():
            line_str = line.strip()
            if line_str.startswith("return redirect("):
                assert "#bank" in line_str, f"{handler.__name__} redirect missing #bank: {line_str}"

