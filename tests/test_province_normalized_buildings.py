"""Province quick-build list must read RealDict rows by name."""
import pytest

pytestmark = pytest.mark.no_server

from app_core.economy.building_costs import enrich_building_row


def test_normalized_buildings_from_realdict_rows():
    rows = [
        {
            "building_id": 3,
            "name": "coal_burners",
            "display_name": "Coal Power Plants",
            "base_cost": 25_000,
        }
    ]
    normalized = [
        enrich_building_row(
            {
                "building_id": r["building_id"],
                "name": r["name"],
                "display_name": r["display_name"],
                "base_cost": r["base_cost"],
            }
        )
        for r in rows
    ]
    assert normalized[0]["name"] == "coal_burners"
    assert "lumber" in normalized[0]["cost_display"].lower()
