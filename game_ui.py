"""
Game UI layer: feature flags, asset manifest, province base layout, Jinja helpers.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import variables

_MANIFEST_PATH = Path(__file__).resolve().parent / "static" / "asset-manifest.json"


def _env_flag(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


# Hybrid visuals — enabled by default; set env to "false" to roll back.
FEATURE_GAME_SHELL = _env_flag("FEATURE_GAME_SHELL", "true")
FEATURE_PROVINCE_BASE_VIEW = _env_flag("FEATURE_PROVINCE_BASE_VIEW", "true")
FEATURE_GAME_PWA = _env_flag("FEATURE_GAME_PWA", "true")

# Legacy JPG filenames (no extension) keyed by normalized building name.
BUILDING_LEGACY_IMAGES: dict[str, str] = {
    "coal_burners": "coalburner.jpg",
    "oil_burners": "oilburner.jpg",
    "solar_fields": "solarfield.jpg",
    "hydro_dams": "hydrodam.jpg",
    "nuclear_reactors": "nuclearreactor.jpg",
    "gas_stations": "gasstation.jpg",
    "general_stores": "generalstore.jpg",
    "farmers_markets": "farmersmarket.jpg",
    "banks": "bank.jpg",
    "malls": "mall.jpg",
    "distribution_centers": "fulfillmentcenters.jpg",
    "industrial_district": "mall.jpg",
    "city_parks": "citypark.png",
    "libraries": "library.jpg",
    "hospitals": "hospital.jpg",
    "universities": "university.jpg",
    "monorails": "skytrain.jpg",
    "primary_school": "library.jpg",
    "high_school": "library.jpg",
    "army_bases": "armybase.png",
    "aerodomes": "aerodrome.png",
    "harbours": "harbour.jpg",
    "admin_buildings": "administrativebuilding.jpg",
    "silos": "silo.jpg",
    "farms": "farm.jpg",
    "pumpjacks": "pumpjack.jpg",
    "coal_mines": "coalmine.jpg",
    "bauxite_mines": "bauxitemine.jpg",
    "copper_mines": "coppermine.jpg",
    "uranium_mines": "uraniummine.jpg",
    "lead_mines": "leadmine.jpg",
    "iron_mines": "ironmine.jpg",
    "lumber_mills": "lumbermill.jpg",
    "component_factories": "componentfactory.jpg",
    "steel_mills": "steelmill.jpg",
    "ammunition_factories": "ammunitionfactory.jpg",
    "aluminium_refineries": "aluminiumrefinery.jpg",
    "oil_refineries": "oilrefinery.jpg",
}

UNIT_LEGACY_IMAGES: dict[str, str] = {
    "soldiers": "soldier.jpg",
    "tanks": "tank.jpg",
    "artillery": "artillery.jpg",
    "fighter_jets": "fighterjet.jpg",
    "bombers": "bomber.jpg",
    "attack_helicopters": "apache.jpg",
    "submarines": "submarine.jpg",
    "cruisers": "cruiser.jpg",
    "destroyers": "destroyer.jpg",
    "spies": "spy.jpg",
    "icbms": "icbm.jpg",
    "nukes": "nuke.jpg",
}

RESOURCE_LEGACY_IMAGES: dict[str, str] = {
    "gold": "resmoney.png",
    "money": "resmoney.png",
    "rations": "resrations.png",
    "oil": "resoil.png",
    "coal": "rescoal.png",
    "uranium": "resuranium.png",
    "bauxite": "resbauxite.png",
    "iron": "resiron.png",
    "lead": "reslead.png",
    "copper": "rescopper.png",
    "lumber": "reslumber.png",
    "components": "rescomponents.png",
    "steel": "ressteel.png",
    "consumer_goods": "resconsumer_goods.png",
    "aluminium": "resaluminium.png",
    "gasoline": "resgasoline.png",
    "ammunition": "resammunition.png",
}

BIOME_LEGACY_IMAGES: dict[str, str] = {
    "tundra": "tundra.jpg",
    "savanna": "savanna.jpg",
    "desert": "desert.jpg",
    "jungle": "jungle.jpg",
    "boreal forest": "borealforest.jpg",
    "borealforest": "borealforest.jpg",
    "grassland": "grassland.jpg",
    "mountain range": "mountainrange.jpg",
    "mountainrange": "mountainrange.jpg",
}

# Slots shown on province base canvas (category → buildings).
PROVINCE_BASE_SLOTS: list[dict[str, Any]] = [
    {
        "id": "power",
        "label": "Power",
        "icon": "bolt",
        "buildings": [
            "coal_burners",
            "oil_burners",
            "solar_fields",
            "hydro_dams",
            "nuclear_reactors",
        ],
    },
    {
        "id": "food",
        "label": "Food",
        "icon": "agriculture",
        "buildings": ["farms"],
    },
    {
        "id": "retail",
        "label": "Retail",
        "icon": "storefront",
        "buildings": [
            "gas_stations",
            "general_stores",
            "farmers_markets",
            "banks",
            "malls",
            "distribution_centers",
        ],
    },
    {
        "id": "mines",
        "label": "Mines",
        "icon": "terrain",
        "buildings": [
            "coal_mines",
            "iron_mines",
            "copper_mines",
            "bauxite_mines",
            "lead_mines",
            "uranium_mines",
            "pumpjacks",
            "lumber_mills",
        ],
    },
    {
        "id": "industry",
        "label": "Industry",
        "icon": "factory",
        "buildings": [
            "component_factories",
            "steel_mills",
            "ammunition_factories",
            "aluminium_refineries",
            "oil_refineries",
            "industrial_district",
        ],
    },
    {
        "id": "civic",
        "label": "Civic",
        "icon": "account_balance",
        "buildings": [
            "city_parks",
            "libraries",
            "hospitals",
            "universities",
            "monorails",
            "primary_school",
            "high_school",
        ],
    },
    {
        "id": "military",
        "label": "Military",
        "icon": "shield",
        "buildings": [
            "army_bases",
            "aerodomes",
            "harbours",
            "admin_buildings",
            "silos",
        ],
    },
]

HUD_STRIP_RESOURCES = ("gold", "rations", "oil", "steel", "consumer_goods")


@lru_cache(maxsize=1)
def load_asset_manifest() -> dict[str, Any]:
    if _MANIFEST_PATH.is_file():
        try:
            with open(_MANIFEST_PATH, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"version": 1, "buildings": {}, "units": {}, "resources": {}}


def legacy_image_for_building(building_key: str) -> str:
    manifest = load_asset_manifest()
    entry = manifest.get("buildings", {}).get(building_key, {})
    if entry.get("legacy"):
        return f"images/{entry['legacy']}"
    legacy = BUILDING_LEGACY_IMAGES.get(building_key)
    if legacy:
        return f"images/{legacy}"
    return "images/province.jpg"


def legacy_image_for_resource(resource_key: str) -> str:
    manifest = load_asset_manifest()
    entry = manifest.get("resources", {}).get(resource_key, {})
    if entry.get("legacy"):
        return f"images/{entry['legacy']}"
    legacy = RESOURCE_LEGACY_IMAGES.get(resource_key)
    if legacy:
        return f"images/{legacy}"
    return "images/resmoney.png"


def legacy_image_for_unit(unit_key: str) -> str:
    manifest = load_asset_manifest()
    entry = manifest.get("units", {}).get(unit_key, {})
    if entry.get("legacy"):
        return f"images/{entry['legacy']}"
    legacy = UNIT_LEGACY_IMAGES.get(unit_key)
    if legacy:
        return f"images/{legacy}"
    return "images/soldier.jpg"


def game_asset_path(kind: str, key: str) -> str:
    """Return static-relative path; prefers manifest game/ override then legacy."""
    manifest = load_asset_manifest()
    bucket = manifest.get(kind, {}).get(key, {})
    if bucket.get("path"):
        return bucket["path"]
    if kind == "buildings":
        return legacy_image_for_building(key)
    if kind == "resources":
        return legacy_image_for_resource(key)
    if kind == "units":
        return legacy_image_for_unit(key)
    return "images/province.jpg"


def biome_background(location: str | None) -> str:
    if not location:
        return "images/grassland.jpg"
    key = location.strip().lower()
    manifest = load_asset_manifest()
    entry = manifest.get("biomes", {}).get(key, {})
    if entry.get("legacy"):
        return f"images/{entry['legacy']}"
    legacy = BIOME_LEGACY_IMAGES.get(key)
    if legacy:
        return f"images/{legacy}"
    return "images/grassland.jpg"


def build_province_layout_payload(province: dict, units: dict) -> dict[str, Any]:
    """JSON-serializable layout for province base canvas."""
    slots = []
    for slot in PROVINCE_BASE_SLOTS:
        total = sum(int(units.get(b, 0) or 0) for b in slot["buildings"])
        dominant = None
        dominant_qty = 0
        for b in slot["buildings"]:
            q = int(units.get(b, 0) or 0)
            if q > dominant_qty:
                dominant_qty = q
                dominant = b
        image_path = (
            legacy_image_for_building(dominant)
            if dominant
            else legacy_image_for_building(slot["buildings"][0])
        )
        slots.append(
            {
                "id": slot["id"],
                "label": slot["label"],
                "icon": slot["icon"],
                "quantity": total,
                "dominant_building": dominant,
                "image": image_path,
                "buildings": slot["buildings"],
            }
        )

    loc = (province.get("location") or "Grassland").strip()
    return {
        "province_id": province.get("id"),
        "name": province.get("name"),
        "location": loc,
        "biome_background": biome_background(loc),
        "happiness": province.get("happiness"),
        "pollution": province.get("pollution"),
        "population": province.get("population"),
        "electricity": province.get("electricity"),
        "slots": slots,
    }


def game_ui_context() -> dict[str, Any]:
    return {
        "FEATURE_GAME_SHELL": FEATURE_GAME_SHELL,
        "FEATURE_PROVINCE_BASE_VIEW": FEATURE_PROVINCE_BASE_VIEW,
        "FEATURE_GAME_PWA": FEATURE_GAME_PWA,
        "game_asset_path": game_asset_path,
        "legacy_image_for_building": legacy_image_for_building,
        "legacy_image_for_resource": legacy_image_for_resource,
        "HUD_STRIP_RESOURCES": HUD_STRIP_RESOURCES,
    }
