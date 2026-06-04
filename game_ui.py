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
_STYLE_CSS_PATH = Path(__file__).resolve().parent / "static" / "style.css"


def get_asset_version() -> str:
    """Cache-bust token tied to deploy commit (or style.css mtime locally)."""
    commit = (
        os.getenv("RAILWAY_GIT_COMMIT_SHA")
        or os.getenv("GIT_COMMIT")
        or os.getenv("SOURCE_VERSION")
    )
    if commit:
        return commit.strip()[:12]
    try:
        return str(int(_STYLE_CSS_PATH.stat().st_mtime))
    except OSError:
        return "dev"


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

# Visual theme per base slot (CSS gradients — no low-res photos).
SLOT_THEMES: dict[str, dict[str, str]] = {
    "power": {
        "gradient": "linear-gradient(145deg, #1a4d6e 0%, #00a7e1 55%, #5cd4f0 100%)",
        "glow": "rgba(0, 167, 225, 0.55)",
        "accent": "#00a7e1",
    },
    "food": {
        "gradient": "linear-gradient(145deg, #1a5c3f 0%, #2d9f6f 55%, #5cd39a 100%)",
        "glow": "rgba(45, 159, 111, 0.5)",
        "accent": "#2d9f6f",
    },
    "retail": {
        "gradient": "linear-gradient(145deg, #5c3d1a 0%, #d4a843 55%, #f0d080 100%)",
        "glow": "rgba(212, 168, 67, 0.5)",
        "accent": "#d4a843",
    },
    "mines": {
        "gradient": "linear-gradient(145deg, #3d3020 0%, #8b6914 55%, #c9a227 100%)",
        "glow": "rgba(201, 162, 39, 0.45)",
        "accent": "#c9a227",
    },
    "industry": {
        "gradient": "linear-gradient(145deg, #3d2a40 0%, #7b4aa8 55%, #b87fd4 100%)",
        "glow": "rgba(123, 74, 168, 0.45)",
        "accent": "#9b6bc4",
    },
    "civic": {
        "gradient": "linear-gradient(145deg, #1a3a5c 0%, #3d7ab8 55%, #7eb8f0 100%)",
        "glow": "rgba(61, 122, 184, 0.45)",
        "accent": "#3d7ab8",
    },
    "military": {
        "gradient": "linear-gradient(145deg, #4a1a1a 0%, #8b3030 55%, #d35649 100%)",
        "glow": "rgba(211, 86, 73, 0.45)",
        "accent": "#d35649",
    },
}

# Material icon per building (province map mini-buildings).
BUILDING_VISUAL_ICONS: dict[str, str] = {
    "coal_burners": "local_fire_department",
    "oil_burners": "oil_barrel",
    "solar_fields": "solar_power",
    "hydro_dams": "water",
    "nuclear_reactors": "science",
    "farms": "agriculture",
    "gas_stations": "local_gas_station",
    "general_stores": "store",
    "farmers_markets": "storefront",
    "banks": "account_balance",
    "malls": "shopping_bag",
    "distribution_centers": "inventory_2",
    "coal_mines": "landscape",
    "iron_mines": "terrain",
    "copper_mines": "brightness_1",
    "bauxite_mines": "grain",
    "lead_mines": "circle",
    "uranium_mines": "radioactive",
    "pumpjacks": "propane",
    "lumber_mills": "forest",
    "component_factories": "precision_manufacturing",
    "steel_mills": "factory",
    "ammunition_factories": "whatshot",
    "aluminium_refineries": "layers",
    "oil_refineries": "water_drop",
    "industrial_district": "domain",
    "city_parks": "park",
    "libraries": "menu_book",
    "hospitals": "local_hospital",
    "universities": "school",
    "monorails": "train",
    "primary_school": "child_care",
    "high_school": "school",
    "army_bases": "military_tech",
    "aerodomes": "flight",
    "harbours": "anchor",
    "admin_buildings": "apartment",
    "silos": "warehouse",
}

BIOME_ICONS: dict[str, str] = {
    "grassland": "grass",
    "tundra": "ac_unit",
    "desert": "wb_sunny",
    "jungle": "forest",
    "savanna": "nature",
    "boreal forest": "park",
    "borealforest": "park",
    "mountain range": "landscape",
    "mountainrange": "landscape",
}

BIOME_THEMES: dict[str, dict[str, str]] = {
    "grassland": {
        "sky": "linear-gradient(180deg, #1a3a5c 0%, #2d6a8f 35%, #4a9e6f 70%, #1a4d32 100%)",
        "ground": "#1e5c38",
    },
    "tundra": {
        "sky": "linear-gradient(180deg, #2a3d52 0%, #6b8aa8 50%, #c8dce8 100%)",
        "ground": "#5a6d78",
    },
    "desert": {
        "sky": "linear-gradient(180deg, #4a2808 0%, #c9862a 45%, #f0d080 100%)",
        "ground": "#8b6914",
    },
    "jungle": {
        "sky": "linear-gradient(180deg, #0d2818 0%, #1a5c32 50%, #2d8f4a 100%)",
        "ground": "#143d24",
    },
    "savanna": {
        "sky": "linear-gradient(180deg, #3d2808 0%, #c9a227 40%, #87ce6a 100%)",
        "ground": "#6b8f2a",
    },
    "boreal forest": {
        "sky": "linear-gradient(180deg, #1a2838 0%, #3d5a6e 55%, #2d4a32 100%)",
        "ground": "#2a4030",
    },
    "borealforest": {
        "sky": "linear-gradient(180deg, #1a2838 0%, #3d5a6e 55%, #2d4a32 100%)",
        "ground": "#2a4030",
    },
    "mountain range": {
        "sky": "linear-gradient(180deg, #1c2029 0%, #5c6b7f 45%, #9eb0c4 100%)",
        "ground": "#4a5568",
    },
    "mountainrange": {
        "sky": "linear-gradient(180deg, #1c2029 0%, #5c6b7f 45%, #9eb0c4 100%)",
        "ground": "#4a5568",
    },
}

# Nation EDIT tab: visual biome picker (value matches stats.location / form POST)
NATION_BIOME_CHOICES: list[dict[str, str]] = [
    {
        "value": "Tundra",
        "label": "Tundra",
        "asset_key": "tundra",
        "tagline": "Frozen frontiers rich in metals",
        "icon": "ac_unit",
    },
    {
        "value": "Savanna",
        "label": "Savanna",
        "asset_key": "savanna",
        "tagline": "Open grasslands and deep deposits",
        "icon": "nature",
    },
    {
        "value": "Desert",
        "label": "Desert",
        "asset_key": "desert",
        "tagline": "Harsh sands, rare treasures",
        "icon": "wb_sunny",
    },
    {
        "value": "Jungle",
        "label": "Jungle",
        "asset_key": "jungle",
        "tagline": "Dense canopy, lumber and oil",
        "icon": "forest",
    },
    {
        "value": "Boreal Forest",
        "label": "Boreal Forest",
        "asset_key": "boreal forest",
        "tagline": "Cold woods and mineral wealth",
        "icon": "park",
    },
    {
        "value": "Grassland",
        "label": "Grassland",
        "asset_key": "grassland",
        "tagline": "Fertile fields and balanced resources",
        "icon": "grass",
    },
    {
        "value": "Mountain Range",
        "label": "Mountain Range",
        "asset_key": "mountain range",
        "tagline": "Rugged peaks, export-grade ore",
        "icon": "landscape",
    },
]


def nation_biome_choices() -> list[dict[str, str]]:
    return NATION_BIOME_CHOICES


def get_slot_config(slot_id: str) -> dict[str, Any] | None:
    for slot in PROVINCE_BASE_SLOTS:
        if slot["id"] == slot_id:
            return slot
    return None


def biome_theme(location: str | None) -> dict[str, str]:
    key = (location or "grassland").strip().lower()
    return BIOME_THEMES.get(key, BIOME_THEMES["grassland"])


def biome_icon(location: str | None) -> str:
    key = (location or "grassland").strip().lower()
    return BIOME_ICONS.get(key, "public")


def building_display_label(name: str) -> str:
    return name.replace("_", " ").title()


def building_visual_icon(name: str) -> str:
    return BUILDING_VISUAL_ICONS.get(name, "domain")


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


def _static_file_exists(relative_path: str) -> bool:
    if not relative_path:
        return False
    rel = relative_path.lstrip("/")
    if rel.startswith("static/"):
        rel = rel[7:]
    return (_MANIFEST_PATH.parent / rel).is_file()


def game_asset_path(kind: str, key: str) -> str:
    """Return static-relative path; prefers manifest game/ override then legacy."""
    manifest = load_asset_manifest()
    bucket = manifest.get(kind, {}).get(key, {})
    game_path = bucket.get("path")
    if game_path and _static_file_exists(game_path):
        return game_path
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
    """JSON-serializable layout for interactive province base."""
    slots = []
    total_structures = 0
    for slot in PROVINCE_BASE_SLOTS:
        theme = SLOT_THEMES.get(slot["id"], SLOT_THEMES["power"])
        breakdown = []
        total = 0
        for b in slot["buildings"]:
            q = int(units.get(b, 0) or 0)
            total += q
            if q > 0:
                breakdown.append(
                    {
                        "name": b,
                        "display_name": building_display_label(b),
                        "icon": building_visual_icon(b),
                        "quantity": q,
                    }
                )
        breakdown.sort(key=lambda x: -x["quantity"])
        total_structures += total
        slots.append(
            {
                "id": slot["id"],
                "label": slot["label"],
                "icon": slot["icon"],
                "quantity": total,
                "buildings": slot["buildings"],
                "breakdown": breakdown[:6],
                "theme": theme,
            }
        )

    loc = (province.get("location") or "Grassland").strip()
    bt = biome_theme(loc)
    happiness = int(province.get("happiness") or 0)
    pollution = int(province.get("pollution") or 0)
    pop = province.get("population") or 0
    return {
        "province_id": province.get("id"),
        "name": province.get("name"),
        "location": loc,
        "biome": bt,
        "biome_icon": biome_icon(loc),
        "happiness": happiness,
        "pollution": pollution,
        "population": pop,
        "population_fmt": f"{int(pop):,}" if pop else "0",
        "electricity": province.get("electricity"),
        "total_structures": total_structures,
        "hub_tier": min(5, max(0, total_structures // 3)),
        "slots": slots,
        "own": province.get("own", True),
    }


def game_ui_context() -> dict[str, Any]:
    return {
        "FEATURE_GAME_SHELL": FEATURE_GAME_SHELL,
        "FEATURE_PROVINCE_BASE_VIEW": FEATURE_PROVINCE_BASE_VIEW,
        "FEATURE_GAME_PWA": FEATURE_GAME_PWA,
        "asset_version": get_asset_version(),
        "game_asset_path": game_asset_path,
        "nation_biome_choices": nation_biome_choices,
        "biome_theme": biome_theme,
        "biome_icon": biome_icon,
        "legacy_image_for_building": legacy_image_for_building,
        "legacy_image_for_resource": legacy_image_for_resource,
        "HUD_STRIP_RESOURCES": HUD_STRIP_RESOURCES,
    }
