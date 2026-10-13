"""Directives: multipliers, fee, and that the shared formulas honour them."""
import pytest

from app_core.directives import services
from app_core.economy.building_costs import land_city_purchase_cost
from app_core.economy.tax_formula import compute_tax_income

pytestmark = pytest.mark.no_server

PROVINCES = [(100000, 10, 20000, 60000, 20000)]


def test_multipliers_ignore_unknown_and_stack():
    assert services.tax_multiplier_for(None) == 1.0
    assert services.tax_multiplier_for({"nope"}) == 1.0
    assert services.tax_multiplier_for({"tax_drive"}) == pytest.approx(1.05)
    assert services.land_price_multiplier_for({"land_drive"}) == pytest.approx(0.90)
    assert services.tax_multiplier_for({"land_drive"}) == 1.0


def test_activation_cost_scales_and_has_floor():
    assert services.activation_cost(0) == services.MIN_COST
    assert services.activation_cost(1_000_000) == 4_000_000


def test_tax_drive_raises_income_by_five_percent():
    base = compute_tax_income(PROVINCES, 0, [0.0], False)["income"]
    boosted = compute_tax_income(PROVINCES, 0, [0.0], False, tax_multiplier=1.05)["income"]
    assert base > 0
    assert boosted == pytest.approx(base * 1.05, abs=2)


def test_land_drive_cuts_land_price_ten_percent():
    full = land_city_purchase_cost("land", 10, 5)
    cut = land_city_purchase_cost("land", 10, 5, price_multiplier=0.90)
    assert full > 0
    assert cut == int(full * 0.90)


def test_tax_drive_pays_back_less_than_its_fee_in_one_week_is_false():
    """Fee is 4h of income, boost yields 5% x 168h = 8.4h: positive but not free."""
    boost_hours = 0.05 * 24 * services.DURATION_DAYS
    assert services.COST_HOURS < boost_hours < 2 * boost_hours


class _FakeDb:
    """Records the params passed to execute; mimics a psycopg2 cursor."""

    def __init__(self, rows=()):
        self.rows = rows
        self.params = None

    def execute(self, sql, params=None):
        self.params = params

    def fetchall(self):
        return self.rows


def test_active_keys_accepts_string_user_id():
    # The country route passes the nation id as a raw URL string. ANY(text[])
    # against an integer column raised "integer = text" and zeroed the income
    # page for every player (found 2026-10-13 via the live get_revenue call).
    db = _FakeDb(rows=[(69697856, "tax_drive")])
    keys = services.active_keys(db, "69697856")
    assert db.params == ([69697856],)
    assert keys == {"tax_drive"}


def test_active_keys_batch_coerces_ids_and_skips_garbage():
    db = _FakeDb()
    services.active_keys_batch(db, ["12", 7, None, "x"])
    assert db.params == ([12, 7],)
    assert services.active_keys(db, "not-a-number") == set()
