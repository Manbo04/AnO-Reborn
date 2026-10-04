import random

from wars.air_defense import (
    IRON_DOME_CAPS,
    STAR_WARS_HARD_CAP,
    calculate_iron_dome_interception,
)


class _Fixed:
    def __init__(self, v):
        self.v = v

    def uniform(self, a, b):
        return self.v


def test_zero_domes_intercept_nothing():
    assert calculate_iron_dome_interception(0, "nukes") == 0.0
    assert calculate_iron_dome_interception(0, "nukes", has_star_wars=True) == 0.0


def test_unknown_projectile_ignored():
    assert calculate_iron_dome_interception(10, "tanks") == 0.0


def test_caps_never_exceeded():
    for proj, cap in IRON_DOME_CAPS.items():
        for n in (1, 5, 10, 1000):
            pct = calculate_iron_dome_interception(n, proj, rng=_Fixed(1.1))
            assert 0 < pct <= cap


def test_more_domes_more_interception():
    r = _Fixed(1.0)
    vals = [calculate_iron_dome_interception(n, "nukes", rng=r) for n in (1, 3, 6, 10)]
    assert vals == sorted(vals) and vals[0] < vals[-1]


def test_star_wars_adds_25_percent_capped():
    r = _Fixed(1.0)
    base = calculate_iron_dome_interception(5, "nukes", rng=r)
    sw = calculate_iron_dome_interception(5, "nukes", has_star_wars=True, rng=r)
    assert abs(sw - base * 1.25) < 1e-9
    top = calculate_iron_dome_interception(1000, "kamikaze_drones", has_star_wars=True, rng=_Fixed(1.1))
    assert top <= STAR_WARS_HARD_CAP


def test_nukes_harder_than_drones():
    r = random.Random(1)
    assert calculate_iron_dome_interception(10, "nukes", rng=_Fixed(1.0)) < \
        calculate_iron_dome_interception(10, "kamikaze_drones", rng=_Fixed(1.0))
