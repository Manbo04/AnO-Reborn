"""Per-province consumer goods, specialisation/integration bonuses, trade fees."""

import math

import pytest

import variables
from app_core.economy.consumer_goods import (
    allocate_consumer_goods,
    cg_tax_multiplier,
    province_cg_capacity,
)
from app_core.economy import industry_bonuses as ib
from app_core.market.fees import trade_fee

# --- consumer goods -------------------------------------------------------


def test_all_local_matches_old_nationwide_result():
    alloc = allocate_consumer_goods([10.0, 20.0], [100.0, 100.0], 1000)
    assert alloc["coverage"] == [1.0, 1.0]
    assert alloc["consumed"] == 30
    assert cg_tax_multiplier(1.0) == pytest.approx(
        variables.CONSUMER_GOODS_TAX_MULTIPLIER
    )


def test_province_without_shops_is_served_remotely_at_reduced_effect(monkeypatch):
    monkeypatch.setattr(variables, "PER_PROVINCE_CG_GRACE_UNTIL", "")
    alloc = allocate_consumer_goods([10.0, 10.0], [100.0, 0.0], 1000)
    assert alloc["coverage"][0] == 1.0
    assert alloc["coverage"][1] == pytest.approx(variables.REMOTE_CG_EFFICIENCY)
    # shipped goods are consumed in full
    assert alloc["consumed"] == 20


def test_no_spare_capacity_leaves_province_unserved():
    alloc = allocate_consumer_goods([10.0, 10.0], [10.0, 0.0], 1000)
    assert alloc["coverage"] == [1.0, 0.0]
    assert alloc["consumed"] == 10


def test_stockpile_shortage_scales_everyone():
    alloc = allocate_consumer_goods([10.0, 10.0], [100.0, 100.0], 10)
    assert alloc["coverage"] == [pytest.approx(0.5), pytest.approx(0.5)]
    assert alloc["consumed"] == 10


def test_no_retail_anywhere():
    alloc = allocate_consumer_goods([10.0], [0.0], 1000)
    assert alloc == {"coverage": [0.0], "consumed": 0, "local": [0.0], "remote": [0.0]}


def test_capacity_from_buildings():
    cap = province_cg_capacity({"malls": 2, "food_banks": 1, "farms": 9})
    per = variables.CONSUMER_GOODS_DISTRIBUTION_PER_BUILDING
    assert cap == 2 * per["malls"] + per["food_banks"]


# --- specialisation / integration ----------------------------------------


def test_scale_bonus_curve():
    assert ib.scale_bonus(0, 10) == 0.0
    assert ib.scale_bonus(5, 0) == 0.0
    half = ib.scale_bonus(5, 10)
    assert half == pytest.approx(
        ib.SCALE_MAX_BONUS * (1 - math.exp(-ib.SCALE_CURVE_K * 0.5))
    )
    assert ib.scale_bonus(10, 10) < ib.SCALE_MAX_BONUS
    assert ib.scale_bonus(1, 10) < ib.scale_bonus(2, 10) < half


def test_power_and_civic_buildings_get_no_bonus():
    for b in ("coal_burners", "universities", "malls", "army_bases"):
        assert ib.production_bonuses(b, {b: 10}, 10, 10, {b: 10})["multiplier"] == 1.0


def test_self_sufficiency_uses_scarcest_input():
    # steel mill: 38 coal + 67 iron per mill
    counts = {"steel_mills": 1, "coal_mines": 1, "iron_mines": 0}
    assert ib.self_sufficiency("steel_mills", counts) == 0.0
    counts["iron_mines"] = 1  # 70 iron >= 67 needed, 120 coal >= 38
    assert ib.self_sufficiency("steel_mills", counts) == 1.0
    counts["steel_mills"] = 2  # iron demand 134, supply 70
    assert ib.self_sufficiency("steel_mills", counts) == pytest.approx(70 / 134)


def test_integration_only_for_processing():
    counts = {"coal_mines": 5, "iron_mines": 5, "steel_mills": 1}
    assert ib.integration_bonus("coal_mines", counts) == 0.0
    assert ib.integration_bonus("steel_mills", counts) == pytest.approx(
        ib.INTEGRATION_MAX_BONUS
    )


def test_industrial_district_uses_city_slots():
    b = ib.production_bonuses(
        "industrial_district", {"industrial_district": 5}, 1000, 10, {}
    )
    assert b["scale"] == pytest.approx(ib.scale_bonus(5, 10))


# --- trade fee ------------------------------------------------------------


def test_trade_fee_rounds_down():
    assert trade_fee(1000, 5) == 50
    assert trade_fee(19, 5) == 0
    assert trade_fee(1000, variables.UNION_TRADE_FEE_PERCENT) == 20


def test_grace_period_counts_shipped_goods_in_full(monkeypatch):
    from datetime import datetime, timezone
    from app_core.economy import consumer_goods as cgm

    monkeypatch.setattr(variables, "PER_PROVINCE_CG_GRACE_UNTIL", "2999-01-01T00:00:00+00:00")
    alloc = allocate_consumer_goods([10.0, 10.0], [100.0, 0.0], 1000)
    assert alloc["coverage"] == [1.0, 1.0]
    past = datetime(3000, 1, 1, tzinfo=timezone.utc)
    assert cgm.remote_cg_efficiency(past) == variables.REMOTE_CG_EFFICIENCY
