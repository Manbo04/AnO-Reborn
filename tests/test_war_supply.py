import pytest
from wars import supply

pytestmark = pytest.mark.no_server

def test_unit_supply_costs():
    costs = supply.unit_supply_costs()
    assert "soldiers" in costs or "infantry" in costs # checking unit existence

def test_defense_supply_budget():
    assert supply.defense_supply_budget(None) == 200
    assert supply.defense_supply_budget(0) == 200
    assert supply.defense_supply_budget(100) == 200
    assert supply.defense_supply_budget(300) == 300
    assert supply.defense_supply_budget(2000) == 2000

def test_pool_after_defense():
    # Only drops down to floor
    assert supply.pool_after_defense(300, 50) == 250
    assert supply.pool_after_defense(300, 150) == 200 # hits floor
    assert supply.pool_after_defense(250, 200) == 200 # hits floor
    assert supply.pool_after_defense(100, 50) == 100 # Already below floor, unchanged
    assert supply.pool_after_defense(0, 50) == 0

def test_ration_defenders():
    costs = {"tanks": 10, "fighters": 15, "soldiers": 2}
    
    # Fully covered
    owned = {"tanks": 5, "soldiers": 50} # 50 + 100 = 150 cost
    fielded, spent = supply.ration_defenders(owned, 200, costs)
    assert fielded == {"tanks": 5, "soldiers": 50}
    assert spent == 150

    # Partially covered
    owned = {"tanks": 20, "fighters": 10} # 200 + 150 = 350 cost
    fielded, spent = supply.ration_defenders(owned, 200, costs)
    # factor = 200 / 350 = 0.5714
    # Tanks: 20 * 0.5714 = 11.4 -> 11
    # Fighters: 10 * 0.5714 = 5.7 -> 5
    assert fielded == {"tanks": 11, "fighters": 5}
    assert spent == 110 + 75 # 185

    # Unusable units
    fielded, spent = supply.ration_defenders(owned, 200, costs, unusable=["fighters"])
    # Only tanks are usable: 20 Tanks -> 200 cost
    assert fielded == {"tanks": 20, "fighters": 0}
    assert spent == 200

def test_citizen_army_pct():
    # 1 province, 1M pop -> ~5%
    pct1 = supply.citizen_army_pct(1_000_000, 1)
    assert 0.04 < pct1 < 0.06

    # 37 provinces, 200M pop -> capped at 25%
    pct_max = supply.citizen_army_pct(200_000_000, 37)
    assert pct_max > 0.24 # ~24.78% or capped at 25%

def test_citizen_army_losses():
    # fixed rng for testing
    class MockRNG:
        def uniform(self, a, b):
            return 1.0 # no variance
            
    losses = supply.citizen_army_losses({"tanks": 100, "soldiers": 1000}, 0.10, rng=MockRNG())
    assert losses == {"tanks": 10, "soldiers": 100}


def test_army_supply_value_counts_only_conventional_units():
    costs = {"soldiers": 1, "tanks": 5, "nukes": 1000}
    assert supply.army_supply_value({"soldiers": 200_000, "tanks": 5000, "nukes": 3}, costs) == 225_000


def test_supply_cap_scales_with_army_but_has_floor():
    assert supply.supply_cap(0) == 2000
    assert supply.supply_cap(4000) == 2000
    assert supply.supply_cap(225_000) == 56_250


def test_hourly_regen_fills_cap_in_about_a_day():
    assert supply.hourly_regen(2000, 20) == 84
    assert supply.hourly_regen(56_250, 20) * 24 >= 56_250
    assert supply.hourly_regen(2000, 20, 1.15) == 97


def test_starting_supplies_favour_the_defender():
    atk, dfn = supply.starting_supplies(56_250, 56_250)
    assert dfn > atk
    assert supply.starting_supplies(2000, 2000) == (400, 1000)
    assert supply.starting_supplies(100, 100) == (200, 200)
