"""Order-book helpers (Market UI Rework, migration 0104)."""
import pytest
import variables
from app_core.market.currency_pricing import classify_offer_currency, gold_normalised

pytestmark = pytest.mark.no_server

ME = 7


def test_gold_offer_is_gold():
    assert classify_offer_currency(None, ME, {}, set()) == "gold"


def test_own_currency_counts_as_held_even_at_zero_balance():
    # A nation can always mint its own currency from gold.
    assert classify_offer_currency(ME, ME, {ME: 0}, set()) == "held"


def test_held_foreign_currency():
    assert classify_offer_currency(42, ME, {42: 3}, {42}) == "held"


def test_zero_balance_but_on_exchange_is_exchange():
    assert classify_offer_currency(42, ME, {42: 0}, {42}) == "exchange"


def test_not_held_not_on_exchange_is_unavailable():
    assert classify_offer_currency(42, ME, {}, {99}) == "unavailable"


def test_gold_normalised_converts_currency_at_fixed_rate():
    assert gold_normalised(100, None) == 100
    assert gold_normalised(20, 42) == 20 * variables.CURRENCY_GOLD_PER_UNIT
