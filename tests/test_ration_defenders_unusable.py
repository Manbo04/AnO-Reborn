"""Defender rationing: unusable units still take the field (2026-10-10)."""

import pytest

from wars.supply import ration_defenders

pytestmark = pytest.mark.no_server

COSTS = {"soldiers": 1, "tanks": 5, "artillery": 3}


def test_unusable_units_are_fielded_at_zero_cost():
    fielded, spent = ration_defenders(
        {"soldiers": 2000, "tanks": 0, "artillery": 0}, 200, COSTS, unusable={"soldiers"}
    )
    assert fielded["soldiers"] == 2000
    assert spent == 0


def test_rationing_never_floors_an_owned_type_to_zero():
    fielded, spent = ration_defenders(
        {"soldiers": 100000, "tanks": 3, "artillery": 0}, 200, COSTS
    )
    assert fielded["tanks"] >= 1
    assert fielded["artillery"] == 0
    assert fielded["soldiers"] > 0


def test_full_army_fielded_when_budget_covers_it():
    fielded, spent = ration_defenders({"soldiers": 50, "tanks": 10}, 500, COSTS)
    assert fielded == {"soldiers": 50, "tanks": 10}
    assert spent == 100


def test_no_units_means_nothing_fielded():
    fielded, spent = ration_defenders({"soldiers": 0, "tanks": 0}, 200, COSTS)
    assert sum(fielded.values()) == 0 and spent == 0
