import pytest
from wars import supply

pytestmark = pytest.mark.no_server

def test_citizen_army_pct():
    # 1 province, 1M pop -> ~5%
    pct1 = supply.citizen_army_pct(1_000_000, 1)
    assert 0.04 < pct1 < 0.06

    # 37 provinces, 200M pop -> capped at 25%
    pct_max = supply.citizen_army_pct(200_000_000, 37)
    assert pct_max > 0.24 # ~24.78% or capped at 25%

def test_citizen_army_losses():
    # fixed rng for testing
    class MockRNG:
        def uniform(self, a, b):
            return 1.0 # no variance
            
    losses = supply.citizen_army_losses({"tanks": 100, "soldiers": 1000}, 0.10, rng=MockRNG())
    assert losses == {"tanks": 10, "soldiers": 100}
