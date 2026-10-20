import math
import pytest
from unittest.mock import MagicMock

import variables
from app_core.economy.building_purchase import (
    BuildingPurchaseError,
    purchase_building,
)
from app_core.economy.consumer_goods import province_cg_need
from services.country_service import CountryService

pytestmark = pytest.mark.no_server


class MockCursor:
    def __init__(self, fetchone_returns=None, fetchall_returns=None):
        self._fetchone = list(fetchone_returns or [])
        self._fetchall = list(fetchall_returns or [])
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        if self._fetchone:
            return self._fetchone.pop(0)
        return None

    def fetchall(self):
        if self._fetchall:
            return self._fetchall.pop(0)
        return []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


# ---------------------------------------------------------------------------
# Problem 1: Country Page Consumer Goods Demand Calculation Tests
# ---------------------------------------------------------------------------

def test_province_cg_need_matches_demographic_formula():
    """Verify province_cg_need accurately reflects demographic weights."""
    rates = variables.DEMO_CONSUMER_GOODS_CONSUMPTION
    pw, pc, pe = 300_000, 200_000, 300_000
    total_pop = pw + pc + pe

    # Without healthcare
    need = province_cg_need(
        population=total_pop,
        pop_children=pc,
        pop_working=pw,
        pop_elderly=pe,
        universal_healthcare=False,
        has_demographic_data=True,
    )
    expected = pw * rates["pop_working"] + pc * rates["pop_children"] + pe * rates["pop_elderly"]
    assert need == expected

    # With healthcare
    need_hc = province_cg_need(
        population=total_pop,
        pop_children=pc,
        pop_working=pw,
        pop_elderly=pe,
        universal_healthcare=True,
        has_demographic_data=True,
    )
    expected_hc = (
        pw * rates["pop_working"]
        + pc * rates["pop_children"]
        + pe * rates["pop_elderly"] * variables.POLICY_HEALTHCARE_ELDERLY_CG_MULTIPLIER
    )
    assert need_hc == expected_hc


def test_country_service_cg_needed_demographic_consumption(monkeypatch):
    """CountryService calculates cg_needed using demographic demand when FEATURE_DEMOGRAPHIC_CONSUMPTION is active."""
    monkeypatch.setattr(variables, "FEATURE_DEMOGRAPHIC_CONSUMPTION", True)
    cId = 16

    # Province 1: 400k pop (150k working, 100k children, 150k elderly)
    # Province 2: 400k pop (150k working, 100k children, 150k elderly)
    prov1 = ("Capital", 1, 400_000, 10, 5, 80, 80, 100_000, 150_000, 150_000)
    prov2 = ("Frontier", 2, 400_000, 10, 5, 80, 80, 100_000, 150_000, 150_000)
    provinces = [prov1, prov2]

    rates = variables.DEMO_CONSUMER_GOODS_CONSUMPTION
    expected_prov_cg = 150_000 * rates["pop_working"] + 100_000 * rates["pop_children"] + 150_000 * rates["pop_elderly"]
    expected_total_cg = math.ceil(expected_prov_cg * 2)  # 15

    # Legacy formula gives math.ceil(800_000 / 80_000) = 10
    assert expected_total_cg != math.ceil(800_000 / variables.CONSUMER_GOODS_PER)
    assert expected_total_cg == 15

    mock_details = (
        "Tester", "desert", "A great nation", "2026-01-01", "flag.png",
        0, "member", "Alliance", 800_000, 80,
        80, 2, "#fff", "star", "Veteran",
        "President", "border-class", "Leader Dede", "Dollar",
        "Party", "Capital",
    )

    db = MockCursor(
        fetchone_returns=[
            mock_details,  # _CORE_COUNTRY_SQL
            (1, "2026-01-01", True),  # users
            (200_000, 300_000, 300_000),  # demographic sum
        ],
        fetchall_returns=[
            provinces,  # provinces
            [],  # resources
            [],  # buildings
            [],  # tech
        ],
    )

    monkeypatch.setattr("database.get_request_cursor", lambda **k: db)
    monkeypatch.setattr("app_core.policies.services.get_user_policies", lambda uid, db=None: {})
    monkeypatch.setattr("helpers.get_influence", lambda uid, db=None: 100)
    monkeypatch.setattr("countries.get_revenue", lambda cid: {"gross": {}, "net": {}})

    res = CountryService.get_country_profile(cId, session_user_id=16)
    assert res["cg_needed"] == expected_total_cg


def test_country_service_cg_needed_universal_healthcare(monkeypatch):
    """CountryService applies elderly healthcare multiplier to cg_needed when policy is active."""
    monkeypatch.setattr(variables, "FEATURE_DEMOGRAPHIC_CONSUMPTION", True)
    cId = 16

    prov = ("Capital", 1, 800_000, 10, 5, 80, 80, 200_000, 300_000, 300_000)
    provinces = [prov]

    rates = variables.DEMO_CONSUMER_GOODS_CONSUMPTION
    elderly_mult = variables.POLICY_HEALTHCARE_ELDERLY_CG_MULTIPLIER
    expected_cg = math.ceil(
        300_000 * rates["pop_working"]
        + 200_000 * rates["pop_children"]
        + 300_000 * rates["pop_elderly"] * elderly_mult
    )  # 17

    mock_details = (
        "Tester", "desert", "A great nation", "2026-01-01", "flag.png",
        0, "member", "Alliance", 800_000, 80,
        80, 1, "#fff", "star", "Veteran",
        "President", "border-class", "Leader Dede", "Dollar",
        "Party", "Capital",
    )

    db = MockCursor(
        fetchone_returns=[
            mock_details,
            (1, "2026-01-01", True),
            (200_000, 300_000, 300_000),
        ],
        fetchall_returns=[
            provinces,
            [],
            [],
            [],
        ],
    )

    monkeypatch.setattr("database.get_request_cursor", lambda **k: db)
    monkeypatch.setattr(
        "app_core.policies.services.get_user_policies",
        lambda uid, db=None: {f"education{variables.POLICY_UNIVERSAL_HEALTHCARE}": True},
    )
    monkeypatch.setattr("helpers.get_influence", lambda uid, db=None: 100)
    monkeypatch.setattr("countries.get_revenue", lambda cid: {"gross": {}, "net": {}})

    res = CountryService.get_country_profile(cId, session_user_id=16)
    assert res["cg_needed"] == expected_cg


def test_country_service_cg_needed_legacy_fallback(monkeypatch):
    """CountryService falls back to population / CONSUMER_GOODS_PER when feature flag is off."""
    monkeypatch.setattr(variables, "FEATURE_DEMOGRAPHIC_CONSUMPTION", False)
    cId = 16

    prov = ("Capital", 1, 800_000, 10, 5, 80, 80, 200_000, 300_000, 300_000)
    provinces = [prov]
    expected_cg = math.ceil(800_000 / variables.CONSUMER_GOODS_PER)  # 10

    mock_details = (
        "Tester", "desert", "A great nation", "2026-01-01", "flag.png",
        0, "member", "Alliance", 800_000, 80,
        80, 1, "#fff", "star", "Veteran",
        "President", "border-class", "Leader Dede", "Dollar",
        "Party", "Capital",
    )

    db = MockCursor(
        fetchone_returns=[
            mock_details,
            (1, "2026-01-01", True),
            (200_000, 300_000, 300_000),
        ],
        fetchall_returns=[
            provinces,
            [],
            [],
            [],
        ],
    )

    monkeypatch.setattr("database.get_request_cursor", lambda **k: db)
    monkeypatch.setattr("app_core.policies.services.get_user_policies", lambda uid, db=None: {})
    monkeypatch.setattr("helpers.get_influence", lambda uid, db=None: 100)
    monkeypatch.setattr("countries.get_revenue", lambda cid: {"gross": {}, "net": {}})

    res = CountryService.get_country_profile(cId, session_user_id=16)
    assert res["cg_needed"] == expected_cg


# ---------------------------------------------------------------------------
# Problem 1: Building Purchase & Mass Purchase Resource Error Logging Tests
# ---------------------------------------------------------------------------

def test_purchase_building_insufficient_iron_for_pumpjacks(monkeypatch):
    """purchase_building rejects pumpjacks when iron is insufficient and gives clear error message."""
    user_id = 16
    province_id = 1

    # Pumpjacks require 22,000 iron
    iron_required = variables.PROVINCE_UNIT_PRICES["pumpjacks_resource"]["iron"]
    assert iron_required == 22_000

    class BuildingMockCursor:
        def __init__(self):
            self.calls = []

        def execute(self, sql, params=None):
            self.calls.append((sql, params))

        def fetchone(self):
            last_sql = self.calls[-1][0].strip().lower() if self.calls else ""
            if "group by" in last_sql:
                return (0, 100)  # free slots: used=0, total=100 -> free=100
            if "from provinces" in last_sql and "for update" in last_sql:
                return (user_id, "desert")  # owner, location (desert allows pumpjacks)
            if "from stats" in last_sql and "location" in last_sql:
                return ("desert",)
            if "from stats" in last_sql and "gold" in last_sql:
                return (10_000_000,)  # ample gold
            if "from user_economy" in last_sql:
                return (5_000,)  # only 5,000 iron available (needs 22,000)
            return None

        def fetchall(self):
            last_sql = self.calls[-1][0].strip().lower() if self.calls else ""
            if "from resource_dictionary" in last_sql:
                return [("iron", 1), ("gold", 2)]
            return []

    cur = BuildingMockCursor()

    with pytest.raises(BuildingPurchaseError) as exc_info:
        purchase_building(
            cur,
            user_id=user_id,
            province_id=province_id,
            building_name="pumpjacks",
            quantity=1,
            policies=[],
        )

    msg = str(exc_info.value)
    assert "Not enough iron" in msg
    assert "need 22,000" in msg
    assert "you have 5,000" in msg
    assert "missing 17,000" in msg


def test_mass_buy_buildings_surfaces_resource_failures(monkeypatch):
    """_mass_buy_buildings records failures and clear error messages when resources run out."""
    import province

    # Mock _plan_mass_purchase to plan 2 provinces
    plan_result = {
        "owned": {1: "North", 2: "South"},
        "plan": [
            {"id": 1, "name": "North", "current": 0, "num": 1, "gold": 50_000},
            {"id": 2, "name": "South", "current": 0, "num": 1, "gold": 50_000},
        ],
        "total_gold": 100_000,
        "total_units": 2,
        "resources": {"iron": 44_000},
    }
    monkeypatch.setattr(province, "_plan_mass_purchase", lambda *a, **k: plan_result)

    call_count = [0]

    def mock_purchase_building(db, user_id, province_id, building_name, quantity, **kwargs):
        call_count[0] += 1
        if province_id == 1:
            return {"building_name": building_name, "quantity": quantity, "gold_spent": 50_000}
        else:
            raise BuildingPurchaseError("Not enough iron: need 22,000, you have 2,000 (missing 20,000). Produce or buy on the market.")

    monkeypatch.setattr(province, "purchase_building", mock_purchase_building)

    dummy_db = MagicMock()
    bought_in, total_spent, owned, failures = province._mass_buy_buildings(
        dummy_db, cId=16, unit="pumpjacks", mode="add", quantity=1, province_ids=[1, 2]
    )

    assert bought_in == 1
    assert total_spent == 50_000
    assert len(failures) == 1
    assert "South: Not enough iron" in failures[0]
