import pytest
from unittest.mock import MagicMock, patch
from collections import defaultdict
import countries


@pytest.mark.no_server
def test_factory_consumption_tracked_and_deducted_when_treasury_empty():
    """
    Test that manufacturing building resource inputs (e.g. 1,800 steel mills
    consuming 120,600 kg/hr iron and 68,400 kg/hr coal) are explicitly tracked in
    factory_consumption and deducted from net, even when the treasury is empty.
    """
    mock_db = MagicMock()

    mock_db.fetchall.side_effect = [
        [(1, 10, 50, 1000, 0, 1000, 0, 0)],  # provinces: id, land, prod, pop, pc, pw, pe, citycount
        [],  # tech_rows
        [(1, "steel_mills", 1800)],  # user_buildings: 1800 steel mills
        [],  # rations distribution buildings
        [],  # load_province_cg_capacities
        [],  # directives (active_keys)
        [],  # military upkeep
        [],  # trade agreements
    ]

    mock_db.fetchone.side_effect = [
        ([],),  # policies
        (0, 1000, 0),  # stats: 0 gold, 1000 rations, 0 consumer_goods
        (1000, 0, 1000, 0, 0),  # workforce
        None,  # coalition member
    ]

    with patch("database.query_cache") as mock_cache, \
         patch("countries.get_coalition_members_table", return_value=None), \
         patch("app_core.economy.tick_order.tax_due_before_next_upkeep", return_value=False):

        mock_cache.get.return_value = None

        rev = countries.get_revenue(12345, db=mock_db)

        # 1800 steel mills * 67 iron = 120,600 kg iron
        # 1800 steel mills * 38 coal = 68,400 kg coal
        assert "factory_consumption" in rev
        assert rev["factory_consumption"]["iron"] == 120600
        assert rev["factory_consumption"]["coal"] == 68400

        # Even with 0 gold treasury, net must accurately reflect factory consumption deficit
        assert rev["net"]["iron"] == -120600
        assert rev["net"]["coal"] == -68400


@pytest.mark.no_server
def test_factory_consumption_with_tech_upgrades():
    """
    Test that tech upgrades adjusting input multipliers (largerforges * 0.7,
    integratedsteelmaking * 1.36, electricarcfurnace * 0.5) are correctly reflected.
    """
    mock_db = MagicMock()

    mock_db.fetchall.side_effect = [
        [(1, 10, 50, 1000, 0, 1000, 0, 0)],
        [("larger_forges",), ("integrated_steelmaking",)],  # techs unlocked
        [(1, "steel_mills", 10)],  # 10 steel mills
        [],  # rations distribution buildings
        [],  # load_province_cg_capacities
        [],  # directives (active_keys)
        [],  # military upkeep
        [],  # trade agreements
    ]

    mock_db.fetchone.side_effect = [
        ([],),
        (100_000_000, 1000, 0),  # plenty of gold
        (1000, 0, 1000, 0, 0),
        None,
    ]

    with patch("database.query_cache") as mock_cache, \
         patch("countries.get_coalition_members_table", return_value=None), \
         patch("app_core.economy.tick_order.tax_due_before_next_upkeep", return_value=True):

        mock_cache.get.return_value = None

        rev = countries.get_revenue(12345, db=mock_db)

        # Base 67 iron * 0.7 * 1.36 = 63.784 per mill -> 637.84 for 10 mills
        # Base 38 coal * 0.7 * 1.36 = 36.176 per mill -> 361.76 for 10 mills
        assert rev["factory_consumption"]["iron"] == pytest.approx(637.84, abs=0.01)
        assert rev["factory_consumption"]["coal"] == pytest.approx(361.76, abs=0.01)
        assert rev["net"]["iron"] == pytest.approx(-637.84, abs=0.01)
        assert rev["net"]["coal"] == pytest.approx(-361.76, abs=0.01)


@pytest.mark.no_server
def test_trade_agreements_flow_and_net_folding():
    """
    Test that active trade agreements calculate hourly flow rate and fold into net revenue.
    """
    mock_db = MagicMock()

    mock_db.fetchall.side_effect = [
        [(1, 10, 50, 1000, 0, 1000, 0, 0)],
        [],
        [],  # no buildings
        [],  # rations distribution buildings
        [],  # load_province_cg_capacities
        [],  # directives (active_keys)
        [],  # military upkeep
        [
            # Agreement 1: cId (12345) is proposer, gives 10,000 steel, gets 50,000 iron every 1 hr
            (12345, "steel", 10000, 99999, "iron", 50000, 1),
            # Agreement 2: cId (12345) is receiver, partner gives 1,000,000 gold, gets 5,000 components every 2 hrs
            (88888, "money", 1000000, 12345, "components", 5000, 2),
        ],
    ]

    mock_db.fetchone.side_effect = [
        ([],),
        (50000, 1000, 0),
        (1000, 0, 1000, 0, 0),
        None,
    ]

    with patch("database.query_cache") as mock_cache, \
         patch("countries.get_coalition_members_table", return_value=None), \
         patch("app_core.economy.tick_order.tax_due_before_next_upkeep", return_value=False):

        mock_cache.get.return_value = None

        rev = countries.get_revenue(12345, db=mock_db)

        assert "trade_agreements_flow" in rev
        flow = rev["trade_agreements_flow"]
        assert flow["steel"] == -10000
        assert flow["iron"] == 50000
        assert flow["money"] == 500000  # 1,000,000 / 2 hours = 500,000/hr
        assert flow["components"] == -2500  # 5,000 / 2 hours = 2,500/hr

        # Check that flows are folded into net
        assert rev["net"]["steel"] == -10000
        assert rev["net"]["iron"] == 50000
        assert rev["net"]["components"] == -2500
        tax = rev["gross"]["money"]
        assert rev["net"]["money"] == tax + 500000


@pytest.mark.no_server
def test_country_templates_render_breakdown_and_tooltips():
    """
    Test that country_v2.html and country.html render factory consumption
    and trade agreement breakdown indicators and Tippy tooltips correctly.
    """
    from app import app
    from flask import render_template_string

    with app.test_request_context("/country/id=1"):
        revenue = {
            "gross": {
                "iron": 5000,
                "money": 100000,
                "rations": 100,
                "consumer_goods": 50,
            },
            "gross_theoretical": {
                "iron": 5000,
                "money": 100000,
                "rations": 100,
                "consumer_goods": 50,
            },
            "net": {
                "iron": -115600,
                "money": 55000,
                "rations": 10,
                "consumer_goods": -20,
            },
            "factory_consumption": {
                "iron": 120600,
            },
            "trade_agreements_flow": {
                "iron": 0,
                "money": 5000,
                "steel": -10000,
            },
            "military_upkeep": {},
            "building_upkeep": 50000,
            "next_tax_income": 100000,
        }
        for r in [
            "coal", "oil", "uranium", "lead", "bauxite", "copper", "lumber",
            "silver", "diamonds", "bullion", "components", "steel",
            "aluminium", "gasoline", "ammunition"
        ]:
            revenue["gross"].setdefault(r, 0)
            revenue["gross_theoretical"].setdefault(r, 0)
            revenue["net"].setdefault(r, 0)

        revenue_daily = {
            "gross": {k: v * 24 for k, v in revenue["gross"].items()},
            "gross_theoretical": {k: v * 24 for k, v in revenue["gross_theoretical"].items()},
            "net": {k: v * 24 for k, v in revenue["net"].items()},
            "factory_consumption": {k: v * 24 for k, v in revenue["factory_consumption"].items()},
            "trade_agreements_flow": {k: v * 24 for k, v in revenue["trade_agreements_flow"].items()},
            "military_upkeep": {},
            "building_upkeep": 1200000,
        }

        from game_ui import game_asset_path

        tpl_v2 = (
            '{% from "macros/revenue.html" import net_resource_card %}'
            '{{ net_resource_card("iron", "Iron", revenue, is_daily=False) }}'
            '{{ net_resource_card("iron", "Iron", revenue_daily, is_daily=True) }}'
        )
        h_v2 = render_template_string(tpl_v2, revenue=revenue, revenue_daily=revenue_daily, game_asset_path=game_asset_path)
        assert "-120.60 t factories" in h_v2 or "120,600 kg factories" in h_v2
        assert "Factory consumption: -" in h_v2
        assert "Iron Breakdown (Hourly)" in h_v2
        assert "Iron Breakdown (Daily)" in h_v2

        tpl_v1 = (
            '{% from "macros/revenue.html" import net_resource_card %}'
            '{{ net_resource_card("iron", "Iron", revenue, is_daily=False) }}'
        )
        h_v1 = render_template_string(tpl_v1, revenue=revenue, game_asset_path=game_asset_path)
        assert "-120.60 t factories" in h_v1 or "120,600 kg factories" in h_v1
        assert "Factory consumption: -" in h_v1
        assert "Iron Breakdown (Hourly)" in h_v1

