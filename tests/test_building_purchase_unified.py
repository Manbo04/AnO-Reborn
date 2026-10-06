"""Unified building purchase uses gold + lumber, not steel."""
import pytest

pytestmark = pytest.mark.no_server

from app_core.economy.building_costs import get_build_cost


def test_coal_burners_cost_is_gold_plus_lumber():
    cost = get_build_cost("coal_burners")
    assert cost["gold"] == 2_500_000
    assert cost["resources"] == {"lumber": 40_000}


def test_farms_cost_gold_plus_lumber_sink():
    # Cash-only after the 2026-06-08 onboarding tweak, then a lumber sink was
    # added on purpose (5912acdf, "balancing, grace period, lumber sink").
    import variables

    cost = get_build_cost("farms")
    assert cost["gold"] == 1_500_000
    assert cost["resources"] == variables.PROVINCE_UNIT_PRICES["farms_resource"]
    assert "steel" not in cost["resources"]
