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


def _js_mirror(slot, n):
    """Python copy of the formula in static/js/province-ui.js slotCostFor()."""
    from app_core.economy.building_costs import LAND_CITY_PRICING

    base, inc, cap = LAND_CITY_PRICING[build_calc.SLOT_UNIT[slot]]
    return base, inc, cap


def test_slot_preview_formula_matches_server_price():
    from app_core.economy.building_costs import land_city_purchase_cost

    for slot in ("city", "land"):
        base, inc, cap = _js_mirror(slot, 0)
        for owned in (0, 10, cap - 3, cap, cap + 40):
            for n in (1, 7, 250):
                unc = max(0, min(n, cap - owned))
                raw = unc * base + inc * (unc * owned + unc * (unc - 1) / 2) + (n - unc) * (base + cap * inc)
                assert int(raw) == land_city_purchase_cost(build_calc.SLOT_UNIT[slot], owned, n, [], 1.0)


def test_slot_cost_unknown_slot_is_none():
    assert build_calc.slot_cost(None, 1, 1, "sky", 5) is None
