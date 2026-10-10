import pytest
pytestmark = pytest.mark.no_server

import sys
from unittest.mock import MagicMock
for _m in [
    "flask",
    "flask_limiter",
    "flask_limiter.util",
    "flask_socketio",
    "flask_login",
    "flask_wtf",
    "flask_wtf.csrf",
    "extensions",
    "psycopg2",
    "psycopg2.extras",
    "psycopg2.pool",
    "psycopg2.extensions",
    "celery",
    "redis",
    "dotenv",
]:
    if _m not in sys.modules:
        try:
            __import__(_m)
        except ImportError:
            sys.modules[_m] = MagicMock()

import datetime
from datetime import timezone

import variables
from wars.aftermath import civilian_death_pct
from wars.routes import (
    STRIKE_TARGET_BUILDINGS,
    STRIKE_TARGET_LABELS,
    STRIKE_TARGET_THRESHOLDS,
    STRIKE_TARGET_GROUPS,
    POPULATION_TARGET,
    _valid_strike_target,
)
from app_core.community.discord_visibility import should_show_discord, get_discord_display_name


def test_a1_distribution_fix_start_date():
    expected = datetime.datetime(2026, 10, 12, 18, 0, 0, tzinfo=timezone.utc)
    assert variables.DISTRIBUTION_FIX_START == expected


def test_a2_growth_freeze_removed():
    # Ensure aftermath module has no freeze constants or freeze_growth function
    import wars.aftermath as aftermath_mod

    assert not hasattr(aftermath_mod, "LOSS_FREEZE_HOURS")
    assert not hasattr(aftermath_mod, "NUKE_FREEZE_HOURS")
    assert not hasattr(aftermath_mod, "freeze_growth")


def test_a3_civilian_death_percentages():
    # Ground: 1% close, 2% definite, 3% annihilation
    assert civilian_death_pct("ground", {}, "close victory") == 0.01
    assert civilian_death_pct("ground", {}, "definite victory") == 0.02
    assert civilian_death_pct("ground", {}, "annihilation") == 0.03

    # Bombers: 2% close, 4% definite, 6% annihilation
    assert civilian_death_pct("air", {"bombers": 10}, "close victory") == 0.02
    assert civilian_death_pct("air", {"bombers": 10}, "definite victory") == 0.04
    assert civilian_death_pct("air", {"bombers": 10}, "annihilation") == 0.06

    # Fighters or naval do not kill civilians
    assert civilian_death_pct("air", {"fighters": 10}, "annihilation") == 0.0
    assert civilian_death_pct("naval", {}, "annihilation") == 0.0


def test_a4_new_province_population_split():
    starting_pop = 10000
    children = int(starting_pop * 0.30)
    working = int(starting_pop * 0.60)
    elderly = int(starting_pop * 0.10)

    assert children == 3000
    assert working == 6000
    assert elderly == 1000
    assert children + working + elderly == 10000


def test_a5_strike_target_buildings_catalog_and_groups():
    # Every strike target building mapped value must exist in variables.BUILDINGS
    for key, bname in STRIKE_TARGET_BUILDINGS.items():
        assert bname in variables.BUILDINGS, f"Building '{bname}' for key '{key}' not in variables.BUILDINGS"
        assert key in STRIKE_TARGET_LABELS, f"Key '{key}' missing from STRIKE_TARGET_LABELS"
        assert key in STRIKE_TARGET_THRESHOLDS, f"Key '{key}' missing from STRIKE_TARGET_THRESHOLDS"
        assert _valid_strike_target(key)

    # Silo is military (15)
    assert STRIKE_TARGET_THRESHOLDS["silo"] == 15

    # Large factories (10)
    for factory in ["steel_mills", "component_factories", "aluminium_refineries", "oil_refineries"]:
        assert factory in STRIKE_TARGET_BUILDINGS
        assert STRIKE_TARGET_THRESHOLDS[factory] == 10

    # Smaller economic buildings (threshold 6)
    smaller_buildings = [
        "farms",
        "pumpjacks",
        "coal_mines",
        "bauxite_mines",
        "copper_mines",
        "uranium_mines",
        "lead_mines",
        "iron_mines",
        "lumber_mills",
        "silver_mines",
        "diamond_mines",
        "bullion_mines",
        "fisheries",
    ]
    for bld in smaller_buildings:
        assert bld in STRIKE_TARGET_BUILDINGS
        assert STRIKE_TARGET_THRESHOLDS[bld] == 6

    # Optgroup definitions
    assert "Military" in STRIKE_TARGET_GROUPS
    assert "Factories" in STRIKE_TARGET_GROUPS
    assert "Mines & resources" in STRIKE_TARGET_GROUPS
    assert STRIKE_TARGET_GROUPS["Military"] == ["silo"]
    assert set(STRIKE_TARGET_GROUPS["Factories"]) == {
        "steel_mills",
        "component_factories",
        "aluminium_refineries",
        "oil_refineries",
    }
    assert set(STRIKE_TARGET_GROUPS["Mines & resources"]) == set(smaller_buildings)

    # Population target
    assert _valid_strike_target(POPULATION_TARGET)


def test_a6_discord_visibility_rule():
    # Off by default / when false
    assert not should_show_discord(False, "discord_user")
    assert not should_show_discord(None, "discord_user")
    assert get_discord_display_name(False, "discord_user") is None

    # Off when no username known even if opt-in is True
    assert not should_show_discord(True, None)
    assert not should_show_discord(True, "")
    assert not should_show_discord(True, "   ")
    assert get_discord_display_name(True, None) is None
    assert get_discord_display_name(True, "") is None

    # On when opt-in is True and username is present
    assert should_show_discord(True, "Player#1234")
    assert get_discord_display_name(True, "Player#1234") == "Player#1234"
    assert get_discord_display_name(True, "  SpacedName  ") == "SpacedName"
