"""Vertical integration must measure what the province really produces.

Discord "Vertical integ bug" (Andy, 2026-10-27): 1,800 aluminium refineries
need 460,800 kg bauxite/h; the province's bauxite mines make 520,400 kg/h
(a 59,600 surplus), yet the page said "56% of inputs produced at home"
because supply was counted at base rates (1000 mines x 260 = 260,000 kg),
ignoring productivity, Stronger Explosives, specialisation and workforce.
"""

import pytest

from app_core.economy.industry_bonuses import (
    INTEGRATION_MAX_BONUS,
    producer_output_multipliers,
    production_bonuses,
    self_sufficiency,
)

pytestmark = pytest.mark.no_server

ANDY = {"bauxite_mines": 1000, "aluminium_refineries": 1800}
UPGRADES = {"strongerexplosives": True}


def test_andys_numbers_base_rate_read_56_percent():
    """The old behaviour, kept as the default when no multipliers are given."""
    assert round(self_sufficiency("aluminium_refineries", ANDY) * 100) == 56


def test_andys_surplus_reads_fully_self_sufficient():
    # Real mine output 520,400 kg/h = 2.0015x the 260 kg base rate.
    mult = {"bauxite_mines": 520_400 / (1000 * 260)}
    assert 1800 * 256 == 460_800
    assert self_sufficiency("aluminium_refineries", ANDY, mult) == 1.0
    bonus = production_bonuses(
        "aluminium_refineries", ANDY, 3000, 0, None, mult
    )
    assert bonus["integration"] == pytest.approx(INTEGRATION_MAX_BONUS)


def test_multipliers_built_like_the_tick_give_full_integration():
    mult = producer_output_multipliers(ANDY, 3000, 0, 100, UPGRADES, 1.0)
    # (productivity 1.45 + project 0.45) x specialisation x workforce 1.0
    assert 1000 * 260 * mult["bauxite_mines"] > 460_800
    assert self_sufficiency("aluminium_refineries", ANDY, mult) == 1.0


def test_partial_shortfall_is_still_proportional():
    counts = {"bauxite_mines": 400, "aluminium_refineries": 1800}
    mult = {"bauxite_mines": 2.0}
    expected = 400 * 260 * 2.0 / 460_800
    assert self_sufficiency("aluminium_refineries", counts, mult) == pytest.approx(expected)


def test_understaffed_workforce_lowers_supply():
    full = producer_output_multipliers(ANDY, 3000, 0, 100, UPGRADES, 1.0)
    short = producer_output_multipliers(ANDY, 3000, 0, 100, UPGRADES, 0.4)
    assert self_sufficiency("aluminium_refineries", ANDY, short) < 1.0
    assert self_sufficiency("aluminium_refineries", ANDY, full) == 1.0


@pytest.mark.parametrize("path", ["province.py", "countries.py", "app_core/game_ticks/revenue.py"])
def test_every_caller_passes_real_output_multipliers(path):
    """Tick, revenue projection and province page must not drift apart."""
    assert "producer_output_multipliers" in open(path, encoding="utf-8").read()
