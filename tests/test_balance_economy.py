"""Money supply, faucet/sink table and loan interest in net income (read-only harness)."""
import datetime as dt
import os

import pytest

from balance import economy, snapshot
from balance.metrics import Nation, summarise
from balance.report import build_report

pytestmark = pytest.mark.no_server

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "balance", "fixtures", "synthetic_snapshot.json")


def _n(i, gold, ai=False, idle=0.0):
    return Nation(idx=i, gold=gold, net_per_hour=10.0, age_days=30.0, idle_days=idle, is_ai=ai)


def test_money_block_splits_humans_and_ai_and_reports_the_median():
    ns = [_n(0, 100), _n(1, 300), _n(2, 200), _n(3, 1000, ai=True), _n(4, 50, idle=30)]
    m = economy.money_block(ns)
    assert m["total_supply"] == 1650
    assert m["human_supply"] == 650 and m["ai_supply"] == 1000
    assert m["median_active_gold"] == 200  # idle nation excluded
    assert m["n_active"] == 3


def test_money_block_handles_no_active_nations():
    m = economy.money_block([_n(0, 5, ai=True)])
    assert m["median_active_gold"] is None and m["top10_share_of_active"] is None


def test_flow_table_classifies_and_never_drops_unknown_categories():
    rows = [
        (dt.date(2026, 11, 6), "tax", 1000, 5),
        (dt.date(2026, 11, 6), "building_upkeep", -400, 5),
        (dt.date(2026, 11, 6), "coalition_tax", -100, 2),
        (dt.date(2026, 11, 7), "tax", 1200, 5),
        (dt.date(2026, 11, 7), "mystery", 77, 1),
    ]
    t = economy.flow_table(rows, loan_interest_per_hour=10)
    assert t["created"] == 2200 and t["destroyed"] == 400 and t["moved"] == -100
    assert t["unclassified"] == 77 and t["categories"]["mystery"]["kind"] == "unclassified"
    assert t["net_supply_change_ledgered"] == 1800
    assert t["net_supply_change_with_loan_interest"] == 1800 - 10 * 24 * 2
    assert [d["day"] for d in t["series"]] == ["2026-11-06", "2026-11-07"]


def test_every_known_category_is_classified():
    from app_core.game_ticks.revenue_history import INCOME_CATEGORIES, SPENDING_CATEGORIES

    for cat in list(INCOME_CATEGORIES) + list(SPENDING_CATEGORIES):
        assert cat in economy.CATEGORY_KIND, f"ledger category {cat!r} has no faucet/sink kind"


def test_not_in_ledger_list_names_the_gaps():
    names = {f for f, _k, _w in economy.UNLEDGERED}
    assert {"loan_interest", "market_trades", "military_upkeep"} <= names


def test_queries_are_single_select_statements():
    snapshot.assert_select_only(economy.FLOWS_SQL)
    snapshot.assert_select_only(economy.LOANS_SQL)
    snapshot.assert_select_only(snapshot.SNAPSHOT_SQL)


def test_loan_interest_is_subtracted_from_net_per_hour():
    now = dt.datetime(2026, 11, 7, tzinfo=dt.timezone.utc)
    rows = [("normal", 1000, "2026-10-01", now, 2400, 30.0), ("normal", 1000, "2026-10-01", now, 2400)]
    with_loan, without = snapshot.anonymise(rows, now)
    pair = sorted([with_loan, without], key=lambda n: n.net_per_hour)
    assert pair[0].net_per_hour == pytest.approx(100.0 - 30.0)
    assert pair[0].loan_interest_per_hour == 30.0
    assert pair[1].net_per_hour == pytest.approx(100.0)


def test_summary_and_report_carry_money_and_flows():
    ns = snapshot.load(FIXTURE)
    assert summarise(ns)["money"]["total_supply"] > 0
    flows = economy.flow_table([(dt.date(2026, 11, 7), "tax", 500, 3)], 5.0)
    flows["active_loans"] = 2
    text, _ok = build_report(ns, "income_scale:1.0", None, flows)
    assert "Money: total supply" in text and "Gold flows" in text and "loan interest" in text
    assert "Not in the ledger:" in text
