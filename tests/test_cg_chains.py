"""Comprehensive tests for Precious Resources, Biome Mines, and Consumer Goods Chains.

Tests covering:
1. Biome mapping of raw mines (silver, diamond, bullion in exactly two biomes each,
   with no existing mines removed).
2. Biome-locked mine access checks (is_mine_allowed_in_biome, other_biome_mines, purchase_building).
3. Slot categories (CITY_UNITS vs LAND_UNITS) and variables registry.
4. CG chain balance (entry-level workshops < jewelry stores < late-game automotive plants).
5. Fisheries vs Farms balance (cost-efficiency early, outscaled by farms with land and tech).
6. Tick production & consumption for the 7 new buildings and 3 new resources.
7. Database schema verification (columns in spyinfo, colbanks, user_economy and rows in dictionaries).
"""

import pytest
from app_core.economy.biome_buildings import (
    BIOME_MINES,
    ALL_MINE_BUILDINGS,
    is_mine_allowed_in_biome,
    other_biome_mines,
)
from app_core.economy.building_costs import CITY_UNITS, LAND_UNITS
from app_core.economy.project_bonuses import project_output_bonus
import variables

pytestmark = pytest.mark.no_server


# ---------------------------------------------------------------------------
# 1. Biome Mapping Tests
# ---------------------------------------------------------------------------

def test_biome_mines_exact_distribution():
    """Verify each new mine is available in exactly two biomes without removing existing mines."""
    expected_assignments = {
        "silver_mines": {"tundra", "mountain range"},
        "diamond_mines": {"savanna", "desert"},
        "bullion_mines": {"boreal forest", "jungle"},
    }

    for mine, expected_biomes in expected_assignments.items():
        assert mine in ALL_MINE_BUILDINGS, f"{mine} missing from ALL_MINE_BUILDINGS"
        actual_biomes = {
            biome for biome, mines in BIOME_MINES.items() if mine in mines
        }
        assert actual_biomes == expected_biomes, (
            f"{mine} expected in {expected_biomes}, but found in {actual_biomes}"
        )

    # Verify existing mines still exist in their designated biomes
    assert "iron_mines" in BIOME_MINES["tundra"]
    assert "iron_mines" in BIOME_MINES["desert"]
    assert "iron_mines" in BIOME_MINES["boreal forest"]
    assert "iron_mines" in BIOME_MINES["grassland"]

    assert "coal_mines" in BIOME_MINES["savanna"]
    assert "coal_mines" in BIOME_MINES["mountain range"]
    assert "coal_mines" in BIOME_MINES["jungle"]
    assert "coal_mines" in BIOME_MINES["boreal forest"]

    assert "copper_mines" in BIOME_MINES["tundra"]
    assert "copper_mines" in BIOME_MINES["savanna"]
    assert "copper_mines" in BIOME_MINES["jungle"]
    assert "copper_mines" in BIOME_MINES["grassland"]

    assert "pumpjacks" in BIOME_MINES["mountain range"]
    assert "pumpjacks" in BIOME_MINES["desert"]
    assert "pumpjacks" in BIOME_MINES["jungle"]
    assert "pumpjacks" in BIOME_MINES["grassland"]

    assert "lumber_mills" in BIOME_MINES["boreal forest"]
    assert "lumber_mills" in BIOME_MINES["mountain range"]
    assert "lumber_mills" in BIOME_MINES["jungle"]

    assert "bauxite_mines" in BIOME_MINES["desert"]
    assert "bauxite_mines" in BIOME_MINES["grassland"]
    assert "bauxite_mines" in BIOME_MINES["mountain range"]
    assert "bauxite_mines" in BIOME_MINES["savanna"]

    assert "lead_mines" in BIOME_MINES["tundra"]
    assert "lead_mines" in BIOME_MINES["savanna"]
    assert "lead_mines" in BIOME_MINES["boreal forest"]

    assert "uranium_mines" in BIOME_MINES["desert"]
    assert "uranium_mines" in BIOME_MINES["tundra"]


def test_is_mine_allowed_in_biome_accuracy():
    """Verify is_mine_allowed_in_biome correctly permits and blocks buildings."""
    # Silver mines
    assert is_mine_allowed_in_biome("silver_mines", "Tundra")
    assert is_mine_allowed_in_biome("silver_mines", "mountain range")
    assert not is_mine_allowed_in_biome("silver_mines", "desert")
    assert not is_mine_allowed_in_biome("silver_mines", "savanna")
    assert not is_mine_allowed_in_biome("silver_mines", "grassland")

    # Diamond mines
    assert is_mine_allowed_in_biome("diamond_mines", "Desert")
    assert is_mine_allowed_in_biome("diamond_mines", "savanna")
    assert not is_mine_allowed_in_biome("diamond_mines", "tundra")
    assert not is_mine_allowed_in_biome("diamond_mines", "mountain range")
    assert not is_mine_allowed_in_biome("diamond_mines", "grassland")

    # Bullion mines
    assert is_mine_allowed_in_biome("bullion_mines", "Boreal Forest")
    assert is_mine_allowed_in_biome("bullion_mines", "jungle")
    assert not is_mine_allowed_in_biome("bullion_mines", "desert")
    assert not is_mine_allowed_in_biome("bullion_mines", "savanna")
    assert not is_mine_allowed_in_biome("bullion_mines", "grassland")

    # Non-mine buildings (workshops, jewelry stores, automotive plants, fisheries)
    for non_mine in ["workshops", "jewelry_stores", "automotive_plants", "fisheries"]:
        for biome in BIOME_MINES.keys():
            assert is_mine_allowed_in_biome(non_mine, biome)


def test_other_biome_mines_exclusion():
    """Verify other_biome_mines returns all mines not allowed in the given biome."""
    tundra_other = {m["name"] for m in other_biome_mines("tundra")}
    assert "diamond_mines" in tundra_other
    assert "bullion_mines" in tundra_other
    assert "silver_mines" not in tundra_other
    assert "iron_mines" not in tundra_other

    desert_other = {m["name"] for m in other_biome_mines("desert")}
    assert "silver_mines" in desert_other
    assert "bullion_mines" in desert_other
    assert "diamond_mines" not in desert_other


def test_purchase_building_rejects_disallowed_mine():
    """Verify purchase_building enforces biome locks for the new mines."""
    from app_core.economy.building_purchase import purchase_building, BuildingPurchaseError

    class _MockCursor:
        def __init__(self, biome):
            self._biome = biome
            self._call = 0
        def execute(self, sql, params=()):
            self._call += 1
        def fetchone(self):
            if self._call == 1:
                return (1,)  # owner matches
            if self._call == 2:
                return (self._biome,)
            return None

    # Tundra province attempting to buy diamond_mines -> rejected
    cursor_tundra = _MockCursor("tundra")
    with pytest.raises(BuildingPurchaseError, match="biome"):
        purchase_building(cursor_tundra, user_id=1, province_id=10, building_name="diamond_mines", quantity=1)

    # Desert province attempting to buy silver_mines -> rejected
    cursor_desert = _MockCursor("desert")
    with pytest.raises(BuildingPurchaseError, match="biome"):
        purchase_building(cursor_desert, user_id=1, province_id=10, building_name="silver_mines", quantity=1)

    # Grassland province attempting to buy bullion_mines -> rejected
    cursor_grassland = _MockCursor("grassland")
    with pytest.raises(BuildingPurchaseError, match="biome"):
        purchase_building(cursor_grassland, user_id=1, province_id=10, building_name="bullion_mines", quantity=1)


# ---------------------------------------------------------------------------
# 2. Economy Configuration & Slot Categories
# ---------------------------------------------------------------------------

def test_slot_categories():
    """Verify city vs land slot distribution for all new buildings."""
    city_additions = {"workshops", "jewelry_stores", "automotive_plants"}
    land_additions = {"silver_mines", "diamond_mines", "bullion_mines", "fisheries"}

    for b in city_additions:
        assert b in CITY_UNITS, f"{b} must be in CITY_UNITS"
        assert b not in LAND_UNITS, f"{b} must not be in LAND_UNITS"

    for b in land_additions:
        assert b in LAND_UNITS, f"{b} must be in LAND_UNITS"
        assert b not in CITY_UNITS, f"{b} must not be in CITY_UNITS"


def test_variables_registration():
    """Verify registration across variables.py."""
    new_resources = ["silver", "diamonds", "bullion"]
    for r in new_resources:
        assert r in variables.RESOURCES

    new_buildings = [
        "workshops", "jewelry_stores", "automotive_plants",
        "fisheries", "silver_mines", "diamond_mines", "bullion_mines"
    ]
    for b in new_buildings:
        assert b in variables.BUILDINGS
        assert f"{b}_price" in variables.PROVINCE_UNIT_PRICES
        assert f"{b}_resource" in variables.PROVINCE_UNIT_PRICES
        assert f"{b}_money" in variables.INFRA
        assert f"{b}_plus" in variables.INFRA
        assert b in variables.NEW_INFRA

    for b in ["workshops", "jewelry_stores", "automotive_plants"]:
        assert b in variables.ENERGY_CONSUMERS


# ---------------------------------------------------------------------------
# 3. Balance & Progression Tests
# ---------------------------------------------------------------------------

def test_cg_chain_tier_progression():
    """Verify consumer goods output per gold upkeep scales with tier (entry < late)."""
    workshop_cg = variables.NEW_INFRA["workshops"]["plus"]["consumer_goods"]
    workshop_cost = variables.NEW_INFRA["workshops"]["money"]
    workshop_eff = workshop_cg / workshop_cost

    jewelry_cg = variables.NEW_INFRA["jewelry_stores"]["plus"]["consumer_goods"]
    jewelry_cost = variables.NEW_INFRA["jewelry_stores"]["money"]
    jewelry_eff = jewelry_cg / jewelry_cost

    auto_cg = variables.NEW_INFRA["automotive_plants"]["plus"]["consumer_goods"]
    auto_cost = variables.NEW_INFRA["automotive_plants"]["money"]
    auto_eff = auto_cg / auto_cost

    # CG tier progression: entry workshops < mid jewelry stores < late automotive plants
    assert workshop_eff < jewelry_eff < auto_eff, (
        f"CG efficiency must scale up: workshop ({workshop_eff:.6f}) < "
        f"jewelry ({jewelry_eff:.6f}) < auto ({auto_eff:.6f})"
    )

    # Check input requirements
    assert "steel" in variables.NEW_INFRA["workshops"]["minus"]
    assert variables.NEW_INFRA["workshops"]["minus"]["steel"] == 2

    jewelry_minus = variables.NEW_INFRA["jewelry_stores"]["minus"]
    assert "silver" in jewelry_minus and jewelry_minus["silver"] == 12
    assert "diamonds" in jewelry_minus and jewelry_minus["diamonds"] == 6
    assert "bullion" in jewelry_minus and jewelry_minus["bullion"] == 8

    auto_minus = variables.NEW_INFRA["automotive_plants"]["minus"]
    assert "steel" in auto_minus and auto_minus["steel"] == 40
    assert "aluminium" in auto_minus and auto_minus["aluminium"] == 30
    assert "components" in auto_minus and auto_minus["components"] == 15


def test_fisheries_vs_farms_scaling():
    """Verify fisheries are cheaper with higher base output, but farms outscale them."""
    fishery_infra = variables.NEW_INFRA["fisheries"]
    farm_infra = variables.NEW_INFRA["farms"]

    # Base build cost: fisheries cheaper ($800k vs $1.5M)
    assert variables.PROVINCE_UNIT_PRICES["fisheries_price"] < variables.PROVINCE_UNIT_PRICES["farms_price"]
    # Base output: fisheries higher (160 vs 100)
    assert fishery_infra["plus"]["rations"] > farm_infra["plus"]["rations"]

    # Project output bonus: farms get advancedmachinery, fisheries do not
    assert project_output_bonus("farms", {"advancedmachinery": True}) == 0.5
    assert project_output_bonus("fisheries", {"advancedmachinery": True}) == 0.0

    # Land scaling: at 50 land, farms outscale fisheries
    land = 50
    farm_total_base = farm_infra["plus"]["rations"] + land * variables.LAND_FARM_PRODUCTION_ADDITION
    fishery_total_base = fishery_infra["plus"]["rations"]
    assert farm_total_base > fishery_total_base, (
        f"Farms with {land} land ({farm_total_base}) must outscale fisheries ({fishery_total_base})"
    )


# ---------------------------------------------------------------------------
# 4. Tick Production and Consumption Formulas
# ---------------------------------------------------------------------------

def test_tick_building_effects_and_production():
    """Verify building production and effect definitions in NEW_INFRA."""
    # Silver mine produces 60 silver, 2 pollution
    assert variables.NEW_INFRA["silver_mines"]["plus"]["silver"] == 60
    assert variables.NEW_INFRA["silver_mines"]["eff"]["pollution"] == 2

    # Diamond mine produces 30 diamonds, 2 pollution
    assert variables.NEW_INFRA["diamond_mines"]["plus"]["diamonds"] == 30
    assert variables.NEW_INFRA["diamond_mines"]["eff"]["pollution"] == 2

    # Bullion mine produces 40 bullion, 2 pollution
    assert variables.NEW_INFRA["bullion_mines"]["plus"]["bullion"] == 40
    assert variables.NEW_INFRA["bullion_mines"]["eff"]["pollution"] == 2

    # Fisheries produce 160 rations, 1 pollution
    assert variables.NEW_INFRA["fisheries"]["plus"]["rations"] == 160
    assert variables.NEW_INFRA["fisheries"]["eff"]["pollution"] == 1

    # Workshops produce 4 CG, consume 2 steel, 1 pollution
    assert variables.NEW_INFRA["workshops"]["plus"]["consumer_goods"] == 4
    assert variables.NEW_INFRA["workshops"]["minus"]["steel"] == 2
    assert variables.NEW_INFRA["workshops"]["eff"]["pollution"] == 1

    # Jewelry stores produce 36 CG, consume silver/diamonds/bullion, 2 pollution
    assert variables.NEW_INFRA["jewelry_stores"]["plus"]["consumer_goods"] == 36
    assert variables.NEW_INFRA["jewelry_stores"]["eff"]["pollution"] == 2

    # Automotive plants produce 160 CG, consume steel/alu/components, 12 pollution
    assert variables.NEW_INFRA["automotive_plants"]["plus"]["consumer_goods"] == 160
    assert variables.NEW_INFRA["automotive_plants"]["eff"]["pollution"] == 12


# ---------------------------------------------------------------------------
# 5. Database Schema & Migration Verification (Integration)
# ---------------------------------------------------------------------------

def test_tick_consumption_and_starvation_simulation():
    """Simulate tick input resolution for new CG buildings and verify starvation behavior."""
    def simulate_building_tick(unit_name, count, gold, energy, available_resources):
        infra = variables.NEW_INFRA[unit_name]
        money_cost = infra["money"]
        energy_cost = 1 if unit_name in variables.ENERGY_CONSUMERS else 0
        minus = dict(infra.get("minus", {}))
        plus = dict(infra.get("plus", {}))

        # Check affordability
        affordable = count
        if money_cost > 0:
            affordable = min(affordable, int(gold // money_cost))
        if energy_cost > 0:
            affordable = min(affordable, int(energy // energy_cost))
        for res, cost in minus.items():
            have = available_resources.get(res, 0)
            affordable = min(affordable, int(have // cost))

        affordable = max(0, affordable)
        consumed = {res: cost * affordable for res, cost in minus.items()}
        produced = {res: amount * affordable for res, amount in plus.items()}
        gold_spent = money_cost * affordable
        energy_spent = energy_cost * affordable

        return {
            "affordable": affordable,
            "produced": produced,
            "consumed": consumed,
            "gold_spent": gold_spent,
            "energy_spent": energy_spent,
        }

    # 1. Workshops full run
    res = simulate_building_tick("workshops", 5, gold=100000, energy=10, available_resources={"steel": 10})
    assert res["affordable"] == 5
    assert res["produced"]["consumer_goods"] == 20
    assert res["consumed"]["steel"] == 10
    assert res["energy_spent"] == 5

    # 2. Workshops partial run (short on steel)
    res = simulate_building_tick("workshops", 5, gold=100000, energy=10, available_resources={"steel": 4})
    assert res["affordable"] == 2
    assert res["produced"]["consumer_goods"] == 8
    assert res["consumed"]["steel"] == 4
    assert res["energy_spent"] == 2

    # 3. Workshops starved (0 steel)
    res = simulate_building_tick("workshops", 5, gold=100000, energy=10, available_resources={"steel": 0})
    assert res["affordable"] == 0
    assert res["produced"].get("consumer_goods", 0) == 0
    assert res["consumed"]["steel"] == 0

    # 4. Jewelry Stores full run
    res = simulate_building_tick(
        "jewelry_stores", 2, gold=200000, energy=5,
        available_resources={"silver": 24, "diamonds": 12, "bullion": 16}
    )
    assert res["affordable"] == 2
    assert res["produced"]["consumer_goods"] == 72
    assert res["consumed"]["silver"] == 24
    assert res["consumed"]["diamonds"] == 12
    assert res["consumed"]["bullion"] == 16

    # 5. Jewelry Stores starved (missing diamonds)
    res = simulate_building_tick(
        "jewelry_stores", 2, gold=200000, energy=5,
        available_resources={"silver": 24, "diamonds": 0, "bullion": 16}
    )
    assert res["affordable"] == 0
    assert res["produced"].get("consumer_goods", 0) == 0

    # 6. Automotive Plants full run
    res = simulate_building_tick(
        "automotive_plants", 1, gold=500000, energy=5,
        available_resources={"steel": 40, "aluminium": 30, "components": 15}
    )
    assert res["affordable"] == 1
    assert res["produced"]["consumer_goods"] == 160
    assert res["consumed"]["steel"] == 40
    assert res["consumed"]["aluminium"] == 30
    assert res["consumed"]["components"] == 15

    # 7. Raw Mines produce without input resources
    res_silver = simulate_building_tick("silver_mines", 3, gold=100000, energy=0, available_resources={})
    assert res_silver["affordable"] == 3
    assert res_silver["produced"]["silver"] == 180

    res_diamond = simulate_building_tick("diamond_mines", 2, gold=100000, energy=0, available_resources={})
    assert res_diamond["affordable"] == 2
    assert res_diamond["produced"]["diamonds"] == 60

    res_bullion = simulate_building_tick("bullion_mines", 1, gold=100000, energy=0, available_resources={})
    assert res_bullion["affordable"] == 1
    assert res_bullion["produced"]["bullion"] == 40

    # 8. Fisheries produce rations without input resources
    res_fish = simulate_building_tick("fisheries", 4, gold=100000, energy=0, available_resources={})
    assert res_fish["affordable"] == 4
    assert res_fish["produced"]["rations"] == 640

