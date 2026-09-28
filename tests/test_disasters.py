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


# ---------------------------------------------------------------------------
# Mitigation tests (new buildings: firewatch_towers, levees, seismic_reinforcements)
# ---------------------------------------------------------------------------

def test_mitigation_multiplier_no_buildings_is_one():
    """With 0 buildings mitigation_multiplier should return 1.0."""
    assert disasters.mitigation_multiplier(0) == pytest.approx(1.0)


def test_mitigation_multiplier_reduces_with_buildings():
    """More buildings → smaller multiplier (more protection)."""
    m100 = disasters.mitigation_multiplier(100)
    m10 = disasters.mitigation_multiplier(10)
    assert m100 < m10 < 1.0


def test_mitigation_multiplier_floor_at_0_1():
    """Very large building counts should bottom-out at 0.1, not reach 0."""
    assert disasters.mitigation_multiplier(1_000_000) == pytest.approx(0.1)


def test_roll_struck_nations_mitigation_reduces_chance():
    """A nation with many mitigation buildings should almost never be struck
    even when the raw RNG value would normally cause a hit."""
    # DISASTER_CHANCE_PER_NATION is 0.001; with 900 buildings the multiplier
    # is 100/1000 = 0.1 → effective chance = 0.0001.  A FixedRng returning
    # 0.0005 is above that threshold, so the nation must NOT be struck.
    nations = [(1, "boreal forest")]
    mitigations = {1: {"firewatch_towers": 900}}
    result = disasters.roll_struck_nations(nations, mitigations=mitigations, rng=FixedRng(0.0005))
    assert result == [], "Nation with heavy mitigation should not be struck at mid-range RNG"


def test_roll_struck_nations_no_mitigation_still_struck():
    """Without mitigation buildings the chance is the baseline value, so a
    FixedRng(0.0) always triggers a strike."""
    nations = [(1, "boreal forest")]
    result = disasters.roll_struck_nations(nations, mitigations={}, rng=FixedRng(0.0))
    assert result == [(1, "boreal forest")]


def test_compute_disaster_loss_mitigation_reduces_loss():
    """Mitigation buildings must reduce the loss fraction."""
    base_loss = disasters.compute_disaster_loss(1_000_000, mitigation_qty=0)
    mitigated_loss = disasters.compute_disaster_loss(1_000_000, mitigation_qty=100)
    assert mitigated_loss < base_loss


def test_compute_disaster_loss_mitigation_floor():
    """Even enormous mitigation qty cannot reduce loss below 10% of base (floor=0.1)."""
    # With mitigation_qty → ∞ fraction → DAMAGE_FRACTION * 0.1
    floor_fraction = disasters.DAMAGE_FRACTION * 0.1
    stockpile = 1_000_000
    expected_floor = int(stockpile * floor_fraction)
    actual = disasters.compute_disaster_loss(stockpile, mitigation_qty=10_000_000)
    assert actual == expected_floor
