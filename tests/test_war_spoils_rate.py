"""End-of-war spoils rates (flag war_spoils_reduced)."""
import pytest

from wars import rules


@pytest.mark.no_server
def test_default_rates_are_unchanged():
    assert rules.standard_spoils_rate(False) == 0.20
    assert rules.standard_spoils_rate(True) == 0.30


@pytest.mark.no_server
def test_reduced_rates_are_lower_and_keep_looting_teams_worth_having():
    low, low_lt = rules.standard_spoils_rate(False, reduced=True), rules.standard_spoils_rate(True, reduced=True)
    assert low < rules.standard_spoils_rate(False)
    assert low_lt < rules.standard_spoils_rate(True)
    assert low_lt > low


@pytest.mark.no_server
def test_conditional_surrender_stays_below_the_standard_rate_in_both_modes():
    for reduced in (False, True):
        for lt in (False, True):
            std = rules.standard_spoils_rate(lt, reduced=reduced)
            assert rules.surrender_spoils_rate("conditional", std) < std
            assert rules.surrender_spoils_rate("unconditional", std) == std
