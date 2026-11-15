"""Pre-calculator payload: same costs the buy charges, shaped for the province page JS."""
from app_core.economy import build_calc
from app_core.economy.building_costs import get_build_cost


def test_unit_costs_match_the_real_buy_cost_helper():
    costs = build_calc._unit_costs([])
    assert costs, "catalogue must not be empty"
    for name in ("coal_burners", "farms", "libraries"):
        if name in costs:
            real = get_build_cost(name, [])
            assert costs[name]["gold"] == int(real["gold"])
            assert costs[name]["resources"] == {r: int(a) for r, a in real["resources"].items()}
    assert all({"gold", "resources", "slot", "jobs"} <= set(c) for c in costs.values())
    assert all(c["slot"] in (None, "city", "land") for c in costs.values())


def test_payload_is_none_for_a_province_the_user_does_not_own():
    class Cur:
        def execute(self, *a, **k):
            pass

        def fetchone(self):
            return None

    assert build_calc.build_calc_payload(Cur(), 1, 2) is None
