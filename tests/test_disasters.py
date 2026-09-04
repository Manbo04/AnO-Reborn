"""Coverage for app_core/game_ticks/disasters.py's pure helpers -- the
random-roll and loss-calculation logic split out specifically so it can be
tested without a database. The DB-touching run_natural_disasters() orchestration
itself mirrors the well-worn task_runs/advisory-lock pattern shared by every
other game_ticks module and isn't re-tested here.
"""
import pytest

from app_core.game_ticks import disasters

pytestmark = pytest.mark.no_server


class FixedRng:
    def __init__(self, value):
        self.value = value

    def random(self):
        return self.value


def test_roll_struck_nations_below_threshold_all_struck():
    nations = [(1, "tundra"), (2, "desert")]
    result = disasters.roll_struck_nations(nations, rng=FixedRng(0.0))
    assert result == nations


def test_roll_struck_nations_above_threshold_none_struck():
    nations = [(1, "tundra"), (2, "desert")]
    result = disasters.roll_struck_nations(nations, rng=FixedRng(0.999))
    assert result == []


def test_roll_struck_nations_ignores_unmapped_biome():
    nations = [(1, "atlantis")]
    result = disasters.roll_struck_nations(nations, rng=FixedRng(0.0))
    assert result == []


def test_biome_disasters_covers_every_canonical_biome():
    # Mirrors app_core/economy/biome_buildings.py's CANONICAL_BIOMES (lowercased) --
    # every biome a nation can actually have should map to a disaster.
    canonical = {"tundra", "desert", "boreal forest", "grassland", "savanna", "mountain range", "jungle"}
    assert canonical == set(disasters.BIOME_DISASTERS.keys())


def test_biome_disasters_message_templates_have_amt_placeholder():
    for label, resource, template in disasters.BIOME_DISASTERS.values():
        assert "{amt}" in template
        assert resource  # non-empty resource name


def test_compute_disaster_loss_zero_when_no_stockpile():
    assert disasters.compute_disaster_loss(0) == 0
    assert disasters.compute_disaster_loss(-5) == 0


def test_compute_disaster_loss_is_fraction_of_stockpile():
    assert disasters.compute_disaster_loss(1000) == 100  # 10%


def test_compute_disaster_loss_capped_for_large_stockpiles():
    huge = 100_000_000
    assert disasters.compute_disaster_loss(huge) == disasters.DAMAGE_CAP_KG
