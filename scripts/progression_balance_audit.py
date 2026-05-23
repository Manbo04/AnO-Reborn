#!/usr/bin/env python3
"""
Static progression balance audit — ROI, gates, tier order, milestone timing.

No database writes. Reads constants from variables.py.

Usage:
  PYTHONPATH=. python3 scripts/progression_balance_audit.py
  PYTHONPATH=. python3 scripts/progression_balance_audit.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import variables  # noqa: E402

# Resources players can obtain without power plants (Tier 0/1 extraction + farms)
TIER1_RESOURCES = {
    "lumber",
    "iron",
    "coal",
    "copper",
    "bauxite",
    "oil",
    "lead",
    "uranium",
    "rations",
    "energy",  # after building power from tier-1 build costs
}

PROCESSED_RESOURCES = {"steel", "aluminium", "gasoline", "components", "ammunition"}

EARLY_PATH = [
    "farms",
    "distribution_centers",
    "coal_burners",
    "lumber_mills",
    "iron_mines",
    "coal_mines",
    "steel_mills",
    "gas_stations",
]

STARTER_GOLD = 80_000_000
STARTER_RESOURCES = {"steel": 15000, "components": 10000, "aluminium": 10000}


@dataclass
class Finding:
    severity: str  # blocker | confusing | minor
    category: str
    building: str
    message: str


def _building_names() -> list[str]:
    return sorted(variables.NEW_INFRA.keys())


def _build_cost(building: str) -> tuple[int, dict[str, int]]:
    price_key = f"{building}_price"
    res_key = f"{building}_resource"
    gold = int(variables.PROVINCE_UNIT_PRICES.get(price_key, 0))
    resources = dict(variables.PROVINCE_UNIT_PRICES.get(res_key, {}) or {})
    return gold, resources


def _net_output_per_tick(building: str) -> dict[str, float]:
    cfg = variables.NEW_INFRA.get(building, {})
    plus = dict(cfg.get("plus") or {})
    minus = dict(cfg.get("minus") or {})
    net: dict[str, float] = {}
    for k, v in plus.items():
        net[k] = net.get(k, 0) + float(v)
    for k, v in minus.items():
        net[k] = net.get(k, 0) - float(v)
    return net


def _upkeep_gold(building: str) -> int:
    return int(variables.NEW_INFRA.get(building, {}).get("money") or 0)


def check_payback(findings: list[Finding]) -> None:
    """Flag buildings whose gold upkeep exceeds plausible gold value of outputs."""
    for name in _building_names():
        cfg = variables.NEW_INFRA.get(name, {})
        plus = cfg.get("plus") or {}
        upkeep = _upkeep_gold(name)
        if upkeep <= 0 or not plus:
            continue
        # Rough: 1 CG ~ 0.5 tax-equivalent gold at DEFAULT_TAX_INCOME scale is fuzzy;
        # flag extreme CG upkeep ratios vs production
        if "consumer_goods" in plus:
            cg = float(plus["consumer_goods"])
            if upkeep > 0 and cg > 0:
                gold_per_cg = upkeep / cg
                if gold_per_cg > 5000:
                    findings.append(
                        Finding(
                            "confusing",
                            "payback",
                            name,
                            f"Gold upkeep ${upkeep:,}/tick for {cg:.0f} CG "
                            f"(${gold_per_cg:,.0f}/CG) — weak retail ROI",
                        )
                    )
        if "rations" in plus:
            r = float(plus["rations"])
            if upkeep > 0 and r > 0 and upkeep / r > 2000:
                findings.append(
                    Finding(
                        "minor",
                        "payback",
                        name,
                        f"Gold upkeep ${upkeep:,}/tick for {r:.0f} rations",
                    )
                )


def check_cg_upkeep_imbalance(findings: list[Finding]) -> None:
    retail = ["gas_stations", "farmers_markets", "general_stores", "malls"]
    rows = []
    for b in retail:
        cfg = variables.NEW_INFRA.get(b, {})
        cg = float((cfg.get("plus") or {}).get("consumer_goods", 0))
        upkeep = _upkeep_gold(b)
        if cg > 0:
            rows.append((b, upkeep, cg, upkeep / cg))
    rows.sort(key=lambda x: x[3], reverse=True)
    if len(rows) >= 2 and rows[0][3] > 2 * rows[-1][3]:
        findings.append(
            Finding(
                "confusing",
                "balance",
                rows[0][0],
                f"Highest $/CG upkeep among retail: "
                f"{rows[0][0]} ${rows[0][1]:,}/{rows[0][2]:.0f} CG "
                f"vs {rows[-1][0]} ${rows[-1][1]:,}/{rows[-1][2]:.0f} CG",
            )
        )


def check_tier_order(findings: list[Finding]) -> None:
    """Build costs requiring processed mats before reasonable production exists."""
    producers = set()
    for name, cfg in variables.NEW_INFRA.items():
        for res in (cfg.get("plus") or {}):
            if res in PROCESSED_RESOURCES or res in TIER1_RESOURCES:
                producers.add(res)
    for name in _building_names():
        _, cost_res = _build_cost(name)
        for res, amt in cost_res.items():
            if res in PROCESSED_RESOURCES and res not in STARTER_RESOURCES:
                # Can player get this without steel_mills etc.?
                tier1_builds = [
                    b
                    for b, c in variables.NEW_INFRA.items()
                    if res in (c.get("plus") or {})
                ]
                early_ok = any(
                    b in ("steel_mills", "aluminium_refineries", "oil_refineries")
                    for b in tier1_builds
                )
                if name in variables.ENERGY_UNITS and res in ("steel", "aluminium"):
                    findings.append(
                        Finding(
                            "blocker",
                            "tier_order",
                            name,
                            f"Power building requires {res} ({amt:,}) — "
                            "circular dependency if coal/oil/solar not tier-1 only",
                        )
                    )
                elif not early_ok and name not in (
                    "hydro_dams",
                    "nuclear_reactors",
                    "malls",
                    "banks",
                ):
                    findings.append(
                        Finding(
                            "confusing",
                            "tier_order",
                            name,
                            f"Build cost needs {res} ({amt:,}); "
                            f"producers: {tier1_builds[:3]}",
                        )
                    )


def check_energy_gate(findings: list[Finding]) -> None:
    for name in variables.ENERGY_CONSUMERS:
        if name not in variables.NEW_INFRA:
            continue
        net = _net_output_per_tick(name)
        if net and "energy" not in (variables.NEW_INFRA.get(name, {}).get("plus") or {}):
            # Consumers need 1 energy per building per revenue tick
            power_options = [
                (b, (variables.NEW_INFRA[b].get("plus") or {}).get("energy", 0))
                for b in variables.ENERGY_UNITS
                if b in variables.NEW_INFRA
            ]
            cheapest = min(
                variables.PROVINCE_UNIT_PRICES.get(f"{b}_price", 10**12)
                for b in variables.ENERGY_UNITS
            )
            findings.append(
                Finding(
                    "minor",
                    "energy",
                    name,
                    f"Requires 1 energy/building/tick; "
                    f"cheapest power build ${cheapest:,}",
                )
            )
            break  # one sample finding only


def check_distribution_vs_production(findings: list[Finding]) -> None:
    for name in _building_names():
        plus = (variables.NEW_INFRA.get(name, {}) or {}).get("plus") or {}
        if "rations" not in plus and "consumer_goods" not in plus:
            continue
        cap = variables.RATIONS_DISTRIBUTION_PER_BUILDING.get(name)
        if "consumer_goods" in plus:
            cap = variables.CONSUMER_GOODS_DISTRIBUTION_PER_BUILDING.get(name, cap)
        if cap and float(plus.get("rations", 0) or plus.get("consumer_goods", 0)) > 0:
            prod = float(plus.get("rations") or plus.get("consumer_goods", 0))
            pop_served = cap
            if prod * 50000 > pop_served / 10:
                findings.append(
                    Finding(
                        "minor",
                        "distribution",
                        name,
                        f"Produces {prod}/tick but caps ~{pop_served:,} pop "
                        "distribution — stockpile can outpace delivery",
                    )
                )


def check_negative_net(findings: list[Finding]) -> None:
    for name in _building_names():
        net = _net_output_per_tick(name)
        if not net:
            continue
        if all(v <= 0 for v in net.values()) and _upkeep_gold(name) > 0:
            findings.append(
                Finding(
                    "confusing",
                    "payback",
                    name,
                    f"Only consumes resources / upkeep ${_upkeep_gold(name):,}; "
                    f"net outputs {net}",
                )
            )


def simulate_early_milestones() -> dict[str, Any]:
    """Estimate gold spend and hours (1 revenue tick/hour) for canonical early path."""
    gold_spent = 0
    steps = []
    resources: dict[str, int] = dict(STARTER_RESOURCES)

    for building in EARLY_PATH:
        gold, cost_res = _build_cost(building)
        missing = {
            k: max(0, v - resources.get(k, 0))
            for k, v in cost_res.items()
        }
        gold_spent += gold
        for k, v in cost_res.items():
            resources[k] = resources.get(k, 0) - v
        cfg = variables.NEW_INFRA.get(building, {})
        for k, v in (cfg.get("plus") or {}).items():
            resources[k] = resources.get(k, 0) + int(v)
        steps.append(
            {
                "building": building,
                "gold_cost": gold,
                "resource_cost": cost_res,
                "missing_after": missing,
                "cumulative_gold": gold_spent,
            }
        )

    province_cost_1 = int(8_000_000 * (1 + 0.16 * 0))
    province_cost_2 = int(8_000_000 * (1 + 0.16 * 1))
    tax_per_million = variables.DEFAULT_TAX_INCOME * 1_000_000

    return {
        "starter_gold": STARTER_GOLD,
        "early_path_gold_total": gold_spent,
        "gold_remaining_after_path": STARTER_GOLD - gold_spent,
        "first_province_cost": province_cost_1,
        "second_province_cost": province_cost_2,
        "rough_tax_per_tick_1M_pop": tax_per_million,
        "steps": steps,
        "hours_to_run_early_path_revenue": len(EARLY_PATH),
    }


def run_audit() -> tuple[list[Finding], dict[str, Any]]:
    findings: list[Finding] = []
    check_payback(findings)
    check_cg_upkeep_imbalance(findings)
    check_tier_order(findings)
    check_energy_gate(findings)
    check_distribution_vs_production(findings)
    check_negative_net(findings)

    # Coal/oil/solar must not require steel/aluminium in build cost
    for power in ("coal_burners", "oil_burners", "solar_fields"):
        _, res = _build_cost(power)
        bad = [k for k in res if k in PROCESSED_RESOURCES]
        if bad:
            findings.append(
                Finding(
                    "blocker",
                    "tier_order",
                    power,
                    f"Build cost includes processed {bad} — blocks early power",
                )
            )

    milestones = simulate_early_milestones()
    order = {"blocker": 0, "confusing": 1, "minor": 2}
    findings.sort(key=lambda f: (order.get(f.severity, 9), f.category, f.building))
    return findings, milestones


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args()

    findings, milestones = run_audit()

    if args.json:
        print(
            json.dumps(
                {
                    "findings": [asdict(f) for f in findings],
                    "milestones": milestones,
                    "feature_flags": {
                        "rations_distribution": variables.FEATURE_RATIONS_DISTRIBUTION,
                        "demographic_consumption": variables.FEATURE_DEMOGRAPHIC_CONSUMPTION,
                        "phase3_workforce": variables.FEATURE_PHASE3_WORKFORCE,
                    },
                },
                indent=2,
            )
        )
        return 0

    print("=" * 80)
    print("PROGRESSION BALANCE AUDIT")
    print("=" * 80)
    print(f"\nFindings: {len(findings)} "
          f"(blocker={sum(1 for f in findings if f.severity=='blocker')}, "
          f"confusing={sum(1 for f in findings if f.severity=='confusing')}, "
          f"minor={sum(1 for f in findings if f.severity=='minor')})\n")

    for f in findings:
        print(f"  [{f.severity.upper():10}] {f.category:12} {f.building:28} {f.message}")

    print("\n" + "-" * 80)
    print("EARLY MILESTONE MODEL (1 building buy per hour)")
    print("-" * 80)
    m = milestones
    print(f"  Starter gold:              ${m['starter_gold']:,}")
    print(f"  Early path total gold:     ${m['early_path_gold_total']:,}")
    print(f"  Gold left after path:      ${m['gold_remaining_after_path']:,}")
    print(f"  1st extra province:        ${m['first_province_cost']:,}")
    print(f"  Tax @ 1M pop/tick:         ${m['rough_tax_per_tick_1M_pop']:,.0f}")
    for step in m["steps"]:
        miss = step["missing_after"]
        flag = " NEEDS MINING" if any(v > 0 for v in miss.values()) else ""
        print(
            f"    {step['building']:24} ${step['gold_cost']:>12,} "
            f"cum=${step['cumulative_gold']:,}{flag}"
        )

    print("\n" + "=" * 80)
    return 1 if any(f.severity == "blocker" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
