"""Numeric guardrails a change must hold (gate 3). Thresholds live here so they are reviewed
in a PR, not argued from memory. Each rule compares a 'before' and an 'after' summary."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

MAX_SHARE_NET_LE_0_RISE = 0.05  # absolute, e.g. 10% -> at most 15%
MAX_MEDIAN_NET_DROP = 0.25  # relative drop in median active net income
MAX_NEW_PLAYER_NET_DROP = 0.20  # new players are protected more tightly
MIN_NEW_PLAYER_NET = 0.0  # a new player must never be pushed below break-even
MAX_GINI_RISE = 0.03  # income inequality may not jump (snowball guard)
MAX_SLOPE_RISE = 0.05  # income-vs-wealth slope may not steepen (snowball guard)


@dataclass
class Result:
    name: str
    ok: bool
    detail: str


def _pct(x: Optional[float]) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def _share_rule(before: dict, after: dict) -> Result:
    b, a = before["share_net_le_0"], after["share_net_le_0"]
    if b is None or a is None:
        return Result("share_net_le_0", False, "no active nations in snapshot")
    ok = (a - b) <= MAX_SHARE_NET_LE_0_RISE + 1e-12
    return Result("share_net_le_0", ok, f"{_pct(b)} -> {_pct(a)} (max rise {MAX_SHARE_NET_LE_0_RISE * 100:.0f} points)")


def _median_rule(before: dict, after: dict) -> Result:
    b, a = before["archetypes"]["median"]["median_net"], after["archetypes"]["median"]["median_net"]
    if not b or b <= 0 or a is None:
        return Result("median_net", False, "median income missing or not positive before the change")
    drop = (b - a) / b
    return Result("median_net", drop <= MAX_MEDIAN_NET_DROP + 1e-12, f"{b:,.0f} -> {a:,.0f} gold/hr ({drop * 100:.1f}% drop, max {MAX_MEDIAN_NET_DROP * 100:.0f}%)")


def _new_player_rule(before: dict, after: dict) -> Result:
    bn, an = before["archetypes"]["new"]["median_net"], after["archetypes"]["new"]["median_net"]
    if bn is None or an is None:
        return Result("new_player_net", True, "no new players in snapshot (not checked)")
    drop = (bn - an) / bn if bn > 0 else 0.0
    ok = drop <= MAX_NEW_PLAYER_NET_DROP + 1e-12 and an >= MIN_NEW_PLAYER_NET
    return Result("new_player_net", ok, f"{bn:,.0f} -> {an:,.0f} gold/hr ({drop * 100:.1f}% drop, max {MAX_NEW_PLAYER_NET_DROP * 100:.0f}%, floor {MIN_NEW_PLAYER_NET:.0f})")


def _snowball_rule(before: dict, after: dict) -> Result:
    bc, ac = before.get("curve") or {}, after.get("curve") or {}
    bg, ag = bc.get("gini_income"), ac.get("gini_income")
    bs, as_ = bc.get("income_wealth_slope"), ac.get("income_wealth_slope")
    if None in (bg, ag, bs, as_):
        return Result("snowball", True, "not enough data to measure the curve (not checked)")
    ok = (ag - bg) <= MAX_GINI_RISE + 1e-12 and (as_ - bs) <= MAX_SLOPE_RISE + 1e-12
    return Result(
        "snowball", ok,
        f"gini {bg:.3f} -> {ag:.3f} (max rise {MAX_GINI_RISE}); income-vs-wealth slope {bs:.2f} -> {as_:.2f} (max rise {MAX_SLOPE_RISE})",
    )


RULES: List[Callable[[dict, dict], Result]] = [_share_rule, _median_rule, _new_player_rule, _snowball_rule]


def evaluate(before: dict, after: dict) -> List[Result]:
    return [rule(before, after) for rule in RULES]


def all_ok(results: List[Result]) -> bool:
    return all(r.ok for r in results)
