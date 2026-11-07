"""Balance harness: metrics, scenarios, guardrails, loop checks, and the SELECT-only guard.
Uses the synthetic fixture only; no database."""
import datetime as dt
import os

import pytest

pytestmark = pytest.mark.no_server

from balance import guardrails, loops, metrics, report, simulate, snapshot

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "balance", "fixtures", "synthetic_snapshot.json")


def nation(i, net, gold=0, age=100, idle=0, ai=False, mil=0):
    return metrics.Nation(idx=i, gold=gold, net_per_hour=net, age_days=age, idle_days=idle, is_ai=ai, military_gold_value=mil)


def test_median_even_odd_empty():
    assert metrics.median([3, 1, 2]) == 2
    assert metrics.median([1, 2, 3, 4]) == 2.5
    assert metrics.median([]) is None


def test_mi_hour_ignores_ai_and_idle():
    ns = [nation(0, 100), nation(1, 300), nation(2, 99999, ai=True), nation(3, 99999, idle=30)]
    assert metrics.mi_hour(ns) == 200


def test_hours_to_afford():
    assert metrics.hours_to_afford(nation(0, 10, gold=100), 50) == 0
    assert metrics.hours_to_afford(nation(0, 10, gold=0), 50) == 5
    assert metrics.hours_to_afford(nation(0, 0, gold=0), 50) == float("inf")
    assert metrics.hours_to_afford(nation(0, -5, gold=0), 50) == float("inf")


def test_archetypes_split():
    ns = [nation(i, 100, gold=i, age=(2 if i < 3 else 100)) for i in range(20)] + [nation(99, 1, ai=True)]
    g = metrics.archetypes(ns)
    assert len(g["new"]) == 3
    assert len(g["ai"]) == 1
    assert len(g["whale"]) == 1  # top 5% of 20 = 1
    assert g["whale"][0].gold == 19


def test_flat_cost_scenario_and_guardrail_pass_for_small_change():
    ns = [nation(i, 1000 + i) for i in range(50)]
    after = simulate.parse_scenario("flat_cost_per_hour:10")(ns)
    results = guardrails.evaluate(metrics.summarise(ns), metrics.summarise(after))
    assert guardrails.all_ok(results)


def test_guardrails_fail_for_crushing_change():
    ns = [nation(i, 1000, age=1) for i in range(50)]
    after = simulate.parse_scenario("flat_cost_per_hour:900")(ns)
    results = guardrails.evaluate(metrics.summarise(ns), metrics.summarise(after))
    assert not guardrails.all_ok(results)
    assert {r.name for r in results if not r.ok} >= {"median_net", "new_player_net"}


def test_income_scale_only_touches_positive_income():
    ns = [nation(0, 100), nation(1, -50)]
    out = simulate.income_scale(0.5)(ns)
    assert out[0].net_per_hour == 50 and out[1].net_per_hour == -50


def test_unknown_scenario_rejected():
    with pytest.raises(ValueError):
        simulate.parse_scenario("magic:1")


def test_raid_loop_detects_free_win():
    # Josh's case: no upkeep, full refund, loot is pure profit.
    assert loops.raid_profit(loot=1_000, unit_cost=500, refund_fraction=1.0) > 0
    # Safe design: partial refund and loot smaller than the sunk cost.
    assert loops.raid_profit(loot=100, unit_cost=500, refund_fraction=0.5) < 0
    assert loops.sellback_round_trip(price=100, refund_fraction=1.0) == 0  # boundary: free, must be capped below 1
    assert loops.sellback_round_trip(price=100, refund_fraction=0.8) < 0


def test_select_only_guard():
    snapshot.assert_select_only("SELECT 1")
    for bad in ("DELETE FROM users", "SELECT 1; DROP TABLE users", "UPDATE stats SET gold=0", "  insert into x values (1)"):
        with pytest.raises(ValueError):
            snapshot.assert_select_only(bad)
    snapshot.assert_select_only(snapshot.SNAPSHOT_SQL)


def test_snapshot_never_falls_back_to_database_url(monkeypatch):
    monkeypatch.delenv("BALANCE_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://prod/db")
    with pytest.raises(RuntimeError):
        snapshot.fetch_nations()


def test_anonymise_drops_identity_and_handles_bad_dates():
    now = dt.datetime(2026, 11, 7, tzinfo=dt.timezone.utc)
    rows = [("bot", 5, "2026-11-06", now, 2400), ("discord", 9, "garbage", None, -480)]
    out = snapshot.anonymise(rows, now, seed=1)
    assert sorted(n.gold for n in out) == [5, 9]
    assert all(not hasattr(n, "user_id") and not hasattr(n, "username") for n in out)
    bot = next(n for n in out if n.is_ai)
    assert bot.net_per_hour == 100 and 0.99 < bot.age_days < 1.01
    human = next(n for n in out if not n.is_ai)
    assert human.age_days == 9999.0 and human.idle_days == 9999.0


def test_fixture_end_to_end_report():
    ns = snapshot.load(FIXTURE)
    assert len(ns) == 600
    text, ok = report.build_report(ns, "flat_cost_per_hour:1000", 50_000_000)
    assert ok and "Guardrails:" in text
    text, ok = report.build_report(ns, "military_upkeep:0.0002", None)
    assert not ok and "BREACHED" in text


def test_gini_equal_and_unequal():
    assert metrics.gini([5, 5, 5, 5]) == pytest.approx(0.0, abs=1e-9)
    assert metrics.gini([0, 0, 0, 100]) == pytest.approx(0.75, abs=1e-9)
    assert metrics.gini([0, 0]) is None and metrics.gini([3]) is None


def test_loglog_slope_detects_taper_and_snowball():
    gold = [10 ** (i / 3) for i in range(1, 16)]
    assert metrics.loglog_slope(gold, [g ** 0.5 for g in gold]) == pytest.approx(0.5, abs=1e-6)
    assert metrics.loglog_slope(gold, [g ** 1.4 for g in gold]) == pytest.approx(1.4, abs=1e-6)
    assert metrics.loglog_slope([1, 2, 3], [1, 2, 3]) is None  # too few points


def test_curve_shape_hibernation_signal():
    ns = [nation(i, 100 + i, gold=1000 * (i + 1), idle=(5 if False else 0.0)) for i in range(20)]
    assert metrics.curve_shape(ns)["top_decile_idle_share"] == 0.0
    ns[-1] = nation(19, 119, gold=10 ** 9, idle=3.0)  # richest, idle 3 days but still active (<=7)
    ns[-2] = nation(18, 118, gold=10 ** 8, idle=3.0)
    assert metrics.curve_shape(ns)["top_decile_idle_share"] == 1.0


def test_snowball_guardrail_trips_when_rich_get_richer():
    ns = [nation(i, 1000 + 10 * i, gold=10 ** 6 * (i + 1)) for i in range(40)]

    def snowball(nations):  # richer nations earn much more after the change
        return [metrics.with_net(n, n.net_per_hour * (1 + n.gold / 10 ** 7)) for n in nations]

    before, after = metrics.summarise(ns), metrics.summarise(snowball(ns))
    res = {r.name: r for r in guardrails.evaluate(before, after)}
    assert not res["snowball"].ok
    flat = metrics.summarise(simulate.flat_cost_per_hour(1)(ns))
    assert {r.name: r for r in guardrails.evaluate(before, flat)}["snowball"].ok
