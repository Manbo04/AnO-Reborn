"""Distribution cap UI helpers and retail upkeep balance."""

import variables
from tasks import compute_rations_distribution_cap, nation_distribution_status


def test_compute_rations_distribution_cap_tiers():
    qty = {
        "gas_stations": 2,
        "malls": 1,
        "distribution_centers": 1,
    }
    expected = (
        2 * variables.RATIONS_DISTRIBUTION_PER_BUILDING["gas_stations"]
        + variables.RATIONS_DISTRIBUTION_PER_BUILDING["malls"]
        + variables.RATIONS_DISTRIBUTION_PER_BUILDING["distribution_centers"]
    )
    assert compute_rations_distribution_cap(qty) == expected


def test_nation_distribution_status_user16_like_bottleneck():
    """12M stockpile, 17M cap, 24M pop — alert + DC suggestion."""
    status = nation_distribution_status(
        total_population=24_200_000,
        rations_stockpile=12_200_000,
        rations_need=484,
        building_qty_by_name={
            "gas_stations": 2,
            "general_stores": 2,
            "malls": 2,
        },
    )
    assert status is not None
    assert status["distribution_cap"] == 17_000_000
    assert status["uncovered_population"] == 7_200_000
    assert status["stockpile_bottleneck"] is True
    assert status["show_alert"] is True
    assert status["distribution_centers_suggested"] == 5


def test_retail_upkeep_gold_per_cg_under_audit_threshold():
    """Progression audit flags retail upkeep above ~$5000/CG."""
    infra = variables.NEW_INFRA
    for name in ("gas_stations", "general_stores", "farmers_markets", "banks", "malls"):
        plus = infra[name].get("plus") or {}
        cg = float(plus.get("consumer_goods") or 0)
        upkeep = int(infra[name].get("money") or 0)
        if cg <= 0:
            continue
        assert upkeep / cg <= 5000, f"{name} upkeep/CG too high: {upkeep / cg}"
