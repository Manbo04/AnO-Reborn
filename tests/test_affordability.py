"""Pure unit tests for app_core/economy/affordability.compute_affordable_units.

No DB, no Flask app -- this is the shared gate both the real hourly tick
(app_core/game_ticks/revenue.py) and the /revenue projection
(countries.get_revenue) call, so these run without any of the live-DB
integration fixtures the rest of the revenue test suite depends on.
"""

import pytest

from app_core.economy.affordability import compute_affordable_units

pytestmark = pytest.mark.no_server


def test_full_run_when_everything_is_affordable():
    units, issues = compute_affordable_units(
        unit_amount=10,
        cost_per_unit=100,
        current_money=10_000,
        energy_per_unit=1,
        current_energy=50,
        per_unit_minus={"bauxite": 5},
        current_resources={"bauxite": 1000},
    )
    assert units == 10
    assert issues == []


def test_money_alone_can_gate_below_full_run():
    units, issues = compute_affordable_units(
        unit_amount=10,
        cost_per_unit=100,
        current_money=350,  # affords 3
        energy_per_unit=0,
        current_energy=0,
        per_unit_minus={},
        current_resources={},
    )
    assert units == 3
    assert issues == ["money"]


def test_energy_shortfall_gates_even_with_full_money_and_input_stock():
    """This is the exact bug class the fix targets: a nation can afford
    upkeep and has plenty of the input resource, but a province has run out
    of local energy -- the building should show as constrained, not full."""
    units, issues = compute_affordable_units(
        unit_amount=10,
        cost_per_unit=10,
        current_money=10_000,  # affords all 10
        energy_per_unit=1,
        current_energy=4,  # only enough energy for 4
        per_unit_minus={"bauxite": 5},
        current_resources={"bauxite": 1_000_000},  # plenty of bauxite
    )
    assert units == 4
    assert "energy" in issues
    assert "money" not in issues


def test_input_resource_shortfall_gates_independently_of_energy_and_money():
    units, issues = compute_affordable_units(
        unit_amount=10,
        cost_per_unit=10,
        current_money=10_000,
        energy_per_unit=1,
        current_energy=10_000,
        per_unit_minus={"bauxite": 100},
        current_resources={"bauxite": 250},  # only enough for 2
    )
    assert units == 2
    assert issues == ["bauxite"]


def test_partial_not_all_or_nothing_across_multiple_gates():
    """The tightest gate wins, and it's never all-or-nothing: 7 of 10
    reactors running on limited uranium is correct, not 0 of 10."""
    units, issues = compute_affordable_units(
        unit_amount=10,
        cost_per_unit=1,
        current_money=10_000,
        energy_per_unit=1,
        current_energy=10_000,
        per_unit_minus={"uranium": 10},
        current_resources={"uranium": 73},  # affords 7 (73 // 10)
    )
    assert units == 7
    assert issues == ["uranium"]


def test_multiple_input_resources_each_apply_independently():
    units, issues = compute_affordable_units(
        unit_amount=10,
        cost_per_unit=1,
        current_money=10_000,
        energy_per_unit=0,
        current_energy=0,
        per_unit_minus={"steel": 10, "aluminium": 10},
        current_resources={"steel": 1_000, "aluminium": 35},  # aluminium caps at 3
    )
    assert units == 3
    assert issues == ["aluminium"]


def test_never_goes_negative_even_with_zero_stock_everywhere():
    units, issues = compute_affordable_units(
        unit_amount=5,
        cost_per_unit=100,
        current_money=0,
        energy_per_unit=1,
        current_energy=0,
        per_unit_minus={"bauxite": 1},
        current_resources={},
    )
    assert units == 0
    assert issues == ["money"]


def test_zero_cost_and_zero_energy_buildings_are_gated_by_resources_only():
    """Buildings with no money upkeep and not in the energy-consumer set
    (e.g. farms) should only ever be gated by their input resources."""
    units, issues = compute_affordable_units(
        unit_amount=4,
        cost_per_unit=0,
        current_money=0,
        energy_per_unit=0,
        current_energy=0,
        per_unit_minus={"lumber": 1000},
        current_resources={"lumber": 1500},  # affords 1
    )
    assert units == 1
    assert issues == ["lumber"]
