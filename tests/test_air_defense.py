import pytest
from wars.air_defense import calculate_sam_interception

def test_calculate_sam_interception_drones():
    class MockRNG:
        def uniform(self, a, b):
            return 1.0

    rng = MockRNG()

    # 0 SAMs = 0%
    assert calculate_sam_interception(0, 'kamikaze_drones', rng) == 0.0

    # 100 SAMs -> cap at 90% for drones
    pct = calculate_sam_interception(100, 'kamikaze_drones', rng)
    assert 0.89 < pct <= 0.90

def test_calculate_sam_interception_missiles():
    class MockRNG:
        def uniform(self, a, b):
            return 1.0

    rng = MockRNG()

    # 100 SAMs -> cap at 80% for missiles
    pct = calculate_sam_interception(100, 'cruise_missiles', rng)
    assert 0.79 < pct <= 0.80

    # Invalid projectile -> 0%
    assert calculate_sam_interception(100, 'icbms', rng) == 0.0

def test_sam_interception_variance():
    class MockHighRNG:
        def uniform(self, a, b):
            return 1.1

    rng = MockHighRNG()
    
    # ensure it never exceeds hard cap even with positive variance
    pct = calculate_sam_interception(200, 'kamikaze_drones', rng)
    assert pct == 0.90
