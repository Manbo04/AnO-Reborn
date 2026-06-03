"""Tests for hybrid game UI module and templates."""
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_server

ROOT = Path(__file__).resolve().parents[1]

from game_ui import (
    FEATURE_GAME_SHELL,
    build_province_layout_payload,
    game_asset_path,
    legacy_image_for_building,
    load_asset_manifest,
)


def test_asset_manifest_loads():
    manifest = load_asset_manifest()
    assert manifest.get("version") == 1
    assert "coal_burners" in manifest.get("buildings", {})


def test_legacy_building_image():
    path = legacy_image_for_building("coal_burners")
    assert path == "images/coalburner.jpg"


def test_game_asset_path_fallback():
    path = game_asset_path("buildings", "coal_burners")
    assert path.endswith(".svg")
    assert "game/buildings" in path


def test_game_asset_path_uses_pilot_svg_when_present():
    path = game_asset_path("resources", "gold")
    assert path.endswith(".svg")
    assert "game/resources" in path


def test_province_layout_payload():
    province = {
        "id": 1,
        "name": "Test Province",
        "location": "Grassland",
        "happiness": 50,
        "pollution": 10,
        "population": 100000,
        "electricity": 5,
    }
    units = {"farms": 2, "coal_burners": 1}
    payload = build_province_layout_payload(province, units)
    assert payload["name"] == "Test Province"
    assert len(payload["slots"]) >= 5
    food_slot = next(s for s in payload["slots"] if s["id"] == "food")
    assert food_slot["quantity"] == 2
    assert payload["total_structures"] == 3
    assert food_slot["breakdown"][0]["icon"] == "agriculture"
    assert payload["biome_icon"] == "grass"


def test_pilot_building_svg_assets_exist():
    for key in ("coal_burners", "farms", "gas_stations"):
        path = game_asset_path("buildings", key)
        assert path.endswith(".svg")
        assert (ROOT / "static" / path).is_file()


def test_jinja_game_macros_compile():
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader("templates"))

    def fake_asset_path(kind, key):
        return game_asset_path(kind, key)

    env.globals.update(
        game_asset_path=fake_asset_path,
        url_for=lambda endpoint, **kw: "/static/" + kw.get("filename", ""),
    )
    env.get_template("macros/game_asset.html")


def test_layout_includes_game_shell_compile():
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader("templates"))
    env.globals.update(
        FEATURE_GAME_SHELL=True,
        FEATURE_GAME_PWA=True,
        FEATURE_PROVINCE_BASE_VIEW=True,
        session={"user_id": 16},
        get_resources=lambda: {"gold": 0, "rations": 0, "oil": 0, "steel": 0, "consumer_goods": 0},
        game_asset_path=game_asset_path,
        HUD_STRIP_RESOURCES=("gold", "rations", "oil", "steel", "consumer_goods"),
        url_for=lambda endpoint, **kw: "/static/" + kw.get("filename", ""),
        admin_user_ids=[],
    )
    env.get_template("partials/game_hud.html")


def test_feature_flags_default_on():
    assert FEATURE_GAME_SHELL is True


def test_province_base_view_renders_meta_and_vitals():
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader("templates"))
    payload = build_province_layout_payload(
        {
            "id": 1,
            "name": "Kaunas",
            "location": "Grassland",
            "happiness": 62,
            "pollution": 18,
            "population": 250000,
            "electricity": 40,
        },
        {"farms": 2},
    )
    html = env.get_template("partials/province_base_view.html").render(
        FEATURE_PROVINCE_BASE_VIEW=True,
        province={"id": 1, "name": "Kaunas"},
        province_base_layout=payload,
        url_for=lambda endpoint, **kw: "/static/" + kw.get("filename", ""),
    )
    assert "province-base-meta" in html
    assert "Grassland" in html
    assert "province-base-vitals" in html
    assert "62%" in html
    assert "Classic view" in html
