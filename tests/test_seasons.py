"""Calendar seasons: meteorological dates, hemisphere flip, biome table."""

import datetime

import pytest

from attack_scripts.combat_helpers import apply_combat_modifiers
from app_core.economy.biome_buildings import CANONICAL_BIOMES
from app_core.economy.seasons import (
    BIOME_PROFILE,
    EFFECTS,
    SEASONS,
    biome_profile,
    days_until_next_season,
    defense_multiplier,
    energy_upkeep_multiplier,
    food_output_multiplier,
    growth_multiplier,
    local_season,
    mood_bonus,
    northern_season,
    season_snapshot,
)

pytestmark = pytest.mark.no_server


def _d(year, month, day):
    return datetime.date(year, month, day)


def test_meteorological_months():
    assert northern_season(3) == "spring"
    assert northern_season(5) == "spring"
    assert northern_season(6) == "summer"
    assert northern_season(8) == "summer"
    assert northern_season(9) == "autumn"
    assert northern_season(11) == "autumn"
    assert northern_season(12) == "winter"
    assert northern_season(1) == "winter"
    assert northern_season(2) == "winter"


def test_boundaries_belong_to_the_new_season():
    assert local_season(_d(2026, 3, 1), "north") == "spring"
    assert local_season(_d(2026, 6, 1), "north") == "summer"
    assert local_season(_d(2026, 9, 1), "north") == "autumn"
    assert local_season(_d(2026, 12, 1), "north") == "winter"
    # Day before the boundary is still the previous season.
    assert local_season(_d(2026, 5, 31), "north") == "spring"
    assert local_season(_d(2026, 2, 28), "north") == "winter"
    assert local_season(_d(2028, 2, 29), "north") == "winter"


def test_days_until_next_season():
    # 31 May is the last day of spring; summer starts 1 Jun.
    assert days_until_next_season(_d(2026, 5, 31)) == 1
    # 1 Mar has just become spring; next boundary is 1 Jun.
    assert days_until_next_season(_d(2026, 3, 1)) == 92
    # 2 Nov 2026 -> 1 Dec is 29 days.
    assert days_until_next_season(_d(2026, 11, 2)) == 29
    # 31 Dec -> 1 Mar the next year. 2027 is not a leap year: 31+28+1 = 60.
    assert days_until_next_season(_d(2026, 12, 31)) == 60
    assert days_until_next_season(_d(2026, 6, 15)) > 0


def test_southern_hemisphere_is_the_opposite_season():
    june = _d(2026, 6, 15)
    december = _d(2026, 12, 15)
    assert local_season(june, "north") == "summer"
    assert local_season(june, "south") == "winter"
    assert local_season(december, "north") == "winter"
    assert local_season(december, "south") == "summer"
    assert local_season(_d(2026, 4, 1), "south") == "autumn"
    assert local_season(_d(2026, 10, 1), "south") == "spring"


def test_every_canonical_biome_resolves():
    for biome in CANONICAL_BIOMES:
        climate, hemisphere = biome_profile(biome)
        assert climate in EFFECTS
        assert hemisphere in ("north", "south")
        snap = season_snapshot(biome, _d(2026, 11, 2))
        assert snap.biome == biome
        assert snap.days_left == 29
        assert snap.season in SEASONS
        assert snap.lines


def test_unknown_biome_defaults_to_temperate_north():
    assert biome_profile(None) == ("temperate", "north")
    assert biome_profile("") == ("temperate", "north")
    assert biome_profile("not a real biome") == ("temperate", "north")
    snap = season_snapshot("Atlantis", _d(2026, 7, 4))
    assert snap.season == "summer"
    assert snap.climate == "temperate"
    assert snap.hemisphere == "north"


def test_savanna_is_southern_tropical_and_jungle_is_northern():
    assert BIOME_PROFILE["savanna"] == ("tropical", "south")
    assert BIOME_PROFILE["jungle"] == ("tropical", "north")
    june = _d(2026, 6, 15)
    jungle = season_snapshot("Jungle", june)
    savanna = season_snapshot("Savanna", june)
    assert jungle.label == "Wet season"
    assert jungle.season == "summer"
    assert savanna.label == "Dry season"
    assert savanna.season == "winter"
    assert savanna.hemisphere == "south"
    # December flips them.
    december = _d(2026, 12, 20)
    assert season_snapshot("Jungle", december).label == "Dry season"
    assert season_snapshot("Savanna", december).label == "Wet season"


def test_hemisphere_override_flips_a_northern_biome():
    june = _d(2026, 6, 15)
    flipped = season_snapshot("Grassland", june, hemisphere="south")
    assert flipped.season == "winter"
    assert flipped.label == "Winter"
    assert flipped.hemisphere == "south"


def test_arctic_winter_defense_and_temperate_has_none():
    january = _d(2027, 1, 10)
    assert defense_multiplier("Tundra", january) == pytest.approx(1.08)
    assert defense_multiplier("Boreal Forest", january) == pytest.approx(1.08)
    assert defense_multiplier("Grassland", january) == 1.0
    # Arctic summer is not a defense bonus.
    assert defense_multiplier("Tundra", _d(2026, 7, 1)) == 1.0
    assert defense_multiplier(None, january) == 1.0


def test_food_and_energy_only_apply_to_a_known_location():
    january = _d(2027, 1, 10)
    assert food_output_multiplier("farms", "Tundra", january) < 1.0
    assert food_output_multiplier("fisheries", "Grassland", _d(2026, 4, 1)) > 1.0
    assert food_output_multiplier("coal_mines", "Tundra", january) == 1.0
    assert food_output_multiplier("farms", None, january) == 1.0
    assert food_output_multiplier("farms", "", january) == 1.0
    assert energy_upkeep_multiplier("Tundra", january) > 1.0
    assert energy_upkeep_multiplier(None, january) == 1.0
    assert growth_multiplier(None) == 1.0
    assert mood_bonus(None) == 0


def test_effect_table_stays_modest_and_complete():
    for climate, seasons in EFFECTS.items():
        assert set(seasons) == set(SEASONS), climate
        for season, fx in seasons.items():
            assert 0.85 <= fx.food <= 1.10, (climate, season, fx.food)
            assert 1.0 <= fx.energy <= 1.12, (climate, season, fx.energy)
            assert 0.95 <= fx.growth <= 1.05, (climate, season, fx.growth)
            assert -2 <= fx.happiness <= 2
            assert 1.0 <= fx.defense <= 1.10
            assert fx.construction == 1.0


def test_snapshot_lines_skip_neutral_effects_and_name_the_real_ones():
    winter = season_snapshot("Tundra", _d(2027, 1, 15))
    text = " ".join(winter.lines)
    assert "Farms and fisheries" in text
    assert "Power use" in text
    assert "Ground defense" in text
    assert "upkeep" not in text.lower()
    spring = season_snapshot("Grassland", _d(2026, 4, 10))
    assert any("Farms and fisheries +" in line for line in spring.lines)
    assert spring.visual == "petals"
    assert winter.visual == "snow"
    assert season_snapshot("Grassland", _d(2026, 7, 1)).visual == "glow"
    assert season_snapshot("Jungle", _d(2026, 7, 1)).visual == "rain"


def test_grassland_autumn_matches_the_calendar_players_can_check():
    snap = season_snapshot("Grassland", _d(2026, 11, 2))
    assert snap.label == "Autumn"
    assert snap.next_label == "Winter"
    assert snap.days_phrase == "29 days"
    assert snap.summary == "Autumn · 29 days until Winter"
    assert snap.icon == "park"
    assert snap.visual == "leaves"


def test_arctic_defense_bonus_scales_ground_defense_only():
    atk_units, atk_bonus, def_units, def_bonus = apply_combat_modifiers(
        10.0, 2.0, 10.0, 4.0, defender_defense_mult=1.08
    )
    assert atk_units == 10.0
    assert atk_bonus == 2.0
    assert def_units == pytest.approx(10.8)
    assert def_bonus == pytest.approx(4.32)

    air = apply_combat_modifiers(
        10.0, 2.0, 10.0, 4.0, is_ground=False, defender_defense_mult=1.08
    )
    assert air == (10.0, 2.0, 10.0, 4.0)
