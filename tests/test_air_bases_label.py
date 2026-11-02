"""Quick Build must say "Air Bases" (not "Aerodromes - Aerodomes cost ...")."""
import pytest

pytestmark = pytest.mark.no_server


def test_air_bases_label_and_cost_text_agree():
    from app_core.economy.building_costs import enrich_building_row

    row = enrich_building_row({"building_id": 15, "name": "aerodomes", "display_name": "Aerodromes", "base_cost": 1})
    assert row["display_name"] == "Air Bases"
    assert row["cost_display"].startswith("Air bases cost $")
    assert "erodom" not in row["cost_display"].lower()


def test_other_buildings_keep_their_dictionary_name():
    from app_core.economy.building_costs import enrich_building_row

    row = enrich_building_row({"building_id": 1, "name": "farms", "display_name": "Farms", "base_cost": 1})
    assert row["display_name"] == "Farms"
