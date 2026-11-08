"""Ledger Lite (experimental, flag-gated): fractional trade fee + sell-back haircut constants."""
from unittest import mock

import variables
from app_core.market import fees


def test_trade_fee_integer_percent_unchanged():
    assert fees.trade_fee(1000, 5) == 50
    assert fees.trade_fee(999, 5) == 49  # rounds down like before


def test_trade_fee_fractional_percent_exact_on_huge_totals():
    total = 10**18 + 7  # beyond float precision
    assert fees.trade_fee(total, "0.5") == (total * 5) // 1000
    assert fees.trade_fee(1000, "0.25") == 2


def test_max_affordable_never_exceeds_gold():
    for pct in (5, "0.5", "0.25", 2):
        for gold in (10**6, 10**12 + 3):
            for price in (3, 997, 10**5):
                n = fees.max_affordable_amount(gold, price, pct)
                total = n * price
                assert total + fees.trade_fee(total, pct) <= gold
                nxt = (n + 1) * price
                assert nxt + fees.trade_fee(nxt, pct) > gold


def test_flag_off_keeps_old_fees():
    with mock.patch("app_core.feature_flags.is_on", return_value=False):
        assert fees.base_fee_percent() == variables.TRADE_FEE_PERCENT
        assert fees.union_fee_percent() == variables.UNION_TRADE_FEE_PERCENT


def test_flag_on_uses_ledger_fees():
    with mock.patch("app_core.feature_flags.is_on", return_value=True):
        assert fees.base_fee_percent() == "0.5"
        assert fees.union_fee_percent() == "0.25"


def test_sellback_haircut_never_returns_more_than_paid():
    pct = variables.LEDGER_SELLBACK_PERCENT
    assert 0 < pct < 100
    assert 1000 * pct // 100 < 1000
