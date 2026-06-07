"""Unified building purchase uses gold + lumber, not steel."""
import pytest

pytestmark = pytest.mark.no_server

from app_core.economy.building_costs import get_build_cost


def test_coal_burners_cost_is_gold_plus_lumber():
    cost = get_build_cost("coal_burners")
    assert cost["gold"] == 2_500_000
    assert cost["resources"] == {"lumber": 40_000}


def test_farms_are_cash_only_after_onboarding_tweak():
    cost = get_build_cost("farms")
    assert cost["gold"] == 1_500_000
    assert cost["resources"] == {}
