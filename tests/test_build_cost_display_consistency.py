"""Build costs must match across formatter, prores, and API enrichment."""
import pytest

pytestmark = pytest.mark.no_server

from app_core.economy.building_costs import enrich_building_row, get_build_cost


@pytest.mark.parametrize(
    "building",
    ["coal_burners", "farms", "lumber_mills", "coal_mines"],
)
def test_build_cost_uses_province_unit_prices_not_steel(building):
    cost = get_build_cost(building)
    display = cost["cost_display"].lower()
    assert "steel" not in display
    if building == "coal_burners":
        assert "lumber" in display
        assert cost["resources"].get("lumber") == 40_000
    if building == "farms":
        assert cost["resources"] == {}
    if building == "lumber_mills":
        assert cost["resources"] == {}


def test_enrich_building_row_matches_formatter():
    row = enrich_building_row(
        {
            "building_id": 1,
            "name": "coal_burners",
            "display_name": "Coal Power Plants",
            "base_cost": 25_000,
        }
    )
    classic = get_build_cost("coal_burners")
    assert row["cost_display"] == classic["cost_display"]
    assert row["gold_cost"] == classic["gold"]
    assert "steel" not in row["cost_display"].lower()
