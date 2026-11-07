"""Before/after report.

    python -m balance.report --snapshot balance/fixtures/synthetic_snapshot.json \\
        --scenario "military_upkeep:0.0005" --cost 5000000

Exit code 1 if any guardrail fails, so it can gate a PR.
"""
from __future__ import annotations

import argparse
import sys

from . import snapshot
from .guardrails import all_ok, evaluate
from .metrics import summarise
from .simulate import parse_scenario

ROWS = [("new", "New player"), ("median", "Median active"), ("whale", "Whale (top 5% gold)"), ("ai", "AI nation")]


def _n(x):
    return "n/a" if x is None else ("never" if x == float("inf") else f"{x:,.1f}")


def build_report(nations, scenario_spec: str, cost: float | None, flows: dict | None = None, activity: dict | None = None) -> tuple[str, bool]:
    before = summarise(nations, cost)
    after = summarise(parse_scenario(scenario_spec)(nations), cost)
    lines = [
        f"Scenario: {scenario_spec}",
        f"Nations: {before['n_total']} total, {before['n_active']} active humans",
        f"MI-hour before: {_n(before['mi_hour'])} gold/hr    after: {_n(after['mi_hour'])} gold/hr",
        "",
        "| Archetype | n | Net/hr before | Net/hr after | Share <=0 before | after |"
        + (" Hours to afford before | after |" if cost is not None else ""),
        "|---|---|---|---|---|---|" + ("---|---|" if cost is not None else ""),
    ]
    for key, label in ROWS:
        b, a = before["archetypes"][key], after["archetypes"][key]
        sh = lambda x: "n/a" if x is None else f"{x * 100:.0f}%"
        row = f"| {label} | {b['n']} | {_n(b['median_net'])} | {_n(a['median_net'])} | {sh(b['share_net_le_0'])} | {sh(a['share_net_le_0'])} |"
        if cost is not None:
            row += f" {_n(b['median_hours_to_afford'])} | {_n(a['median_hours_to_afford'])} |"
        lines.append(row)
    bc, ac = before["curve"], after["curve"]
    f = lambda x, d=3: "n/a" if x is None else f"{x:.{d}f}"
    lines += [
        "",
        f"Curve: gini {f(bc['gini_income'])} -> {f(ac['gini_income'])}; income-vs-wealth slope {f(bc['income_wealth_slope'], 2)} -> {f(ac['income_wealth_slope'], 2)}; "
        f"top-10% income share {f(bc['top_decile_income_share'], 2)} -> {f(ac['top_decile_income_share'], 2)}; "
        f"richest 10% idle >2d: {f(bc['top_decile_idle_share'], 2)}",
    ]
    bm, am = before["money"], after["money"]
    g = lambda x: "n/a" if x is None else f"{x:,.0f}"
    lines += [
        f"Money: total supply {g(bm['total_supply'])} (humans {g(bm['human_supply'])}, AI {g(bm['ai_supply'])}); "
        f"median active nation holds {g(bm['median_active_gold'])}; top 10% of active hold "
        f"{f(bm['top10_share_of_active'], 2)} of active gold",
    ]
    if flows:
        c = flows["categories"]
        lines += ["", f"Gold flows, last {len(flows['days'])} days (ledger): created {g(flows['created'])}, "
                  f"destroyed {g(flows['destroyed'])}, moved to coalition banks {g(flows['moved'])}"]
        lines += [f"- {k} ({v['kind']}): {g(v['total'])}" for k, v in c.items()]
        lines += [f"- loan interest (sink, not in ledger, inferred upper bound): {g(flows['loan_interest_per_hour_inferred'])}/hr "
                  f"across {flows.get('active_loans', 0)} active loans"]
        lines += ["Not in the ledger: " + "; ".join(f"{x['flow']} ({x['kind']})" for x in flows["not_in_ledger"])]
    rt = before["retention"]
    pct = lambda x: "n/a" if x is None else f"{x * 100:.0f}%"
    lines += ["", "Retention (last seen on or after day N; " + rt["basis"] + "): " + "; ".join(
        f"D{d} {pct(rt[f'd{d}']['rate'])} ({rt[f'd{d}']['retained']}/{rt[f'd{d}']['matured']}, "
        f"{rt[f'd{d}']['no_activity_record']} with no activity record)" for d in (1, 7, 30))]
    if activity is not None:
        if activity["collecting"]:
            lines += ["", "What players do: no counter data yet (flag activity_counters off or just enabled)."]
        else:
            lines += ["", f"What players do ({activity['days_with_data']} days of counters; top10 = richest 10% of active humans):"]
            for cohort in ("top10", "new", "other"):
                c = activity["cohorts"].get(cohort)
                if c:
                    lines.append(f"- {cohort} ({c['total']} actions): " + ", ".join(
                        f"{a['action']} {a['share'] * 100:.0f}%" for a in c["actions"][:6]))
    results = evaluate(before, after)
    lines += ["", "Guardrails:"]
    lines += [f"- {'PASS' if r.ok else 'FAIL'} {r.name}: {r.detail}" for r in results]
    ok = all_ok(results)
    lines.append("")
    lines.append("RESULT: " + ("all guardrails hold" if ok else "GUARDRAIL BREACHED, revise the change"))
    return "\n".join(lines), ok


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--snapshot", help="snapshot JSON file (see balance/README.md)")
    p.add_argument("--live", action="store_true", help="read BALANCE_DATABASE_URL (read-only) instead of a file")
    p.add_argument("--save", help="with --live, also save the anonymised snapshot to this path")
    p.add_argument("--scenario", required=True)
    p.add_argument("--cost", type=float, help="reference cost in gold for the hours-to-afford column")
    a = p.parse_args(argv)
    if a.live:
        nations = snapshot.fetch_nations()
        flows = snapshot.fetch_flows()
        activity_data = snapshot.fetch_activity()
        if a.save:
            snapshot.save(nations, a.save)
    elif a.snapshot:
        nations = snapshot.load(a.snapshot)
        flows = None
        activity_data = None
    else:
        p.error("give --snapshot FILE or --live")
    text, ok = build_report(nations, a.scenario, a.cost, flows, activity_data)
    print(text)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
