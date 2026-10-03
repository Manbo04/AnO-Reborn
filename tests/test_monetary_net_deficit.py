import pytest
from unittest.mock import MagicMock, patch
import countries

@pytest.mark.no_server
def test_monetary_net_deducts_full_building_upkeep_when_treasury_empty():
    """
    Regression test for the bug reported by Kurai:
    When a nation has an empty treasury or building upkeep exceeds tax income,
    monetary net must reflect the true deficit (tax - upkeep) rather than
    omitting unaffordable buildings and falsely reporting a positive profit.
    """
    mock_db = MagicMock()

    mock_db.fetchall.side_effect = [
        [(1, 10, 50, 1000, 0, 1000, 0, 0)],  # provinces: id, land, prod, pop, pc, pw, pe, citycount
        [],  # tech_rows
        [(1, "steel_mills", 10)],  # user_buildings: 10 steel mills = 600,000 upkeep
        [],  # load_province_cg_capacities
        [],  # rations distribution buildings
        [],  # military upkeep
    ]

    mock_db.fetchone.side_effect = [
        ([],),  # policies: education/active policies array
        (0, 1000, 0),  # stats: 0 gold, 1000 rations, 0 consumer_goods
        (1000, 0, 1000, 0, 0),  # workforce
        None,  # coalition member
    ]

    with patch("database.query_cache") as mock_cache, \
         patch("countries.get_coalition_members_table", return_value=None), \
         patch("app_core.economy.tick_order.tax_due_before_next_upkeep", return_value=False):

        mock_cache.get.return_value = None

        rev = countries.get_revenue(12345, db=mock_db)

        # 10 steel mills upkeep = 600,000
        assert rev["building_upkeep"] == 600000
        tax = rev["gross"]["money"]
        # In the bug, rev["net"]["money"] was +tax (and skipped all 600k upkeep because treasury was 0)
        # With the fix, rev["net"]["money"] must accurately deduct 600,000 upkeep
        assert rev["net"]["money"] == tax - 600000
        assert rev["net"]["money"] < 0


@pytest.mark.no_server
def test_monetary_net_deducts_full_building_upkeep_when_upkeep_exceeds_tax_budget():
    """
    Even when tax lands before upkeep (tax_due_before_next_upkeep is True),
    if upkeep > tax income, the portion exceeding the tax income must NOT be skipped.
    Monetary net must be negative.
    """
    mock_db = MagicMock()

    mock_db.fetchall.side_effect = [
        [(1, 10, 50, 1000, 0, 1000, 0, 0)],
        [],
        [(1, "steel_mills", 10)],  # 10 steel mills = 600,000 upkeep
        [],  # load_province_cg_capacities
        [],  # rations distribution buildings
        [],  # military upkeep
    ]

    mock_db.fetchone.side_effect = [
        ([],),  # policies
        (0, 1000, 0),  # 0 treasury gold
        (1000, 0, 1000, 0, 0),
        None,
    ]

    with patch("database.query_cache") as mock_cache, \
         patch("countries.get_coalition_members_table", return_value=None), \
         patch("app_core.economy.tick_order.tax_due_before_next_upkeep", return_value=True):

        mock_cache.get.return_value = None

        rev = countries.get_revenue(12345, db=mock_db)

        assert rev["building_upkeep"] == 600000
        tax = rev["gross"]["money"]
        assert rev["net"]["money"] == tax - 600000
        assert rev["net"]["money"] < 0
