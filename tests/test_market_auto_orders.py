"""compute_top_up: every limit is ANDed (Helios' auto sell/buy orders)."""
import pytest
from app_core.market.auto_orders import compute_top_up, describe_rule

pytestmark = pytest.mark.no_server


def sell(**kw):
    args = dict(stock=10_000, on_offer=0, added_24h=0, reserve_limit=None,
                max_offer=None, max_per_day=None)
    args.update(kw)
    return compute_top_up("sell", **args)


def buy(**kw):
    args = dict(stock=0, on_offer=0, added_24h=0, reserve_limit=None,
                max_offer=None, max_per_day=None, affordable_units=10_000)
    args.update(kw)
    return compute_top_up("buy", **args)


def test_helios_example_tops_up_the_smaller_gap():
    # 500 max offer, 500/day: 380 still listed, 120 added today -> add 120.
    assert sell(on_offer=380, added_24h=120, max_offer=500, max_per_day=500)[0] == 120


def test_daily_limit_binds():
    units, reason = sell(on_offer=0, added_24h=500, max_offer=500, max_per_day=500)
    assert units == 0 and "Daily limit" in reason


def test_offer_full_binds():
    units, reason = sell(on_offer=500, added_24h=0, max_offer=500, max_per_day=1000)
    assert units == 0 and "Offer is full" in reason


def test_sell_reserve_binds():
    units, reason = sell(stock=1_100, reserve_limit=1_000, max_offer=500)
    assert units == 100
    units, reason = sell(stock=300, reserve_limit=300, max_offer=500)
    assert units == 0 and "Reserves at minimum" in reason


def test_sell_never_more_than_stock():
    assert sell(stock=40, max_offer=500)[0] == 40


def test_buy_reserve_counts_what_is_already_on_offer():
    # Target 1,000: hold 600 + 300 already bidding -> only 100 more.
    assert buy(stock=600, on_offer=300, reserve_limit=1_000, max_offer=5_000)[0] == 100
    units, reason = buy(stock=900, on_offer=100, reserve_limit=1_000, max_offer=5_000)
    assert units == 0 and "Reserve target" in reason


def test_buy_capped_by_funds():
    units, reason = buy(max_per_day=500, affordable_units=37)
    assert units == 37
    units, reason = buy(max_per_day=500, affordable_units=0)
    assert units == 0 and "Not enough funds" in reason


def test_rule_without_offer_or_daily_cap_never_posts():
    units, reason = sell(stock=10_000)
    assert units == 0 and "needs a maximum" in reason


def test_never_negative():
    assert sell(on_offer=900, added_24h=900, max_offer=500, max_per_day=500)[0] == 0
    assert buy(stock=5_000, reserve_limit=1_000, max_offer=500)[0] == 0


def test_describe_rule_reads_like_the_form_preview():
    text = describe_rule("sell", "iron", 236, "gold", None, 500, 500)
    assert text == "Sell iron at 236 gold, keep up to 500 on offer, add at most 500 per 24h."
    text = describe_rule("buy", "oil", 50, "Marks", 2_000, None, 100)
    assert text == "Buy oil at 50 Marks, add at most 100 per 24h, stop once you hold 2,000."
