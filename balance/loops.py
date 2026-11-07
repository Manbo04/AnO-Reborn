"""Exploit-loop checks (gate 2) expressed as numbers, so they can run in tests and reports."""
from __future__ import annotations


def sellback_round_trip(price: float, refund_fraction: float, fee_fraction: float = 0.0) -> float:
    """Gold gained by buying something and selling it straight back. Must be < 0 to be safe."""
    return price * refund_fraction * (1 - fee_fraction) - price


def raid_profit(loot: float, unit_cost: float, refund_fraction: float, upkeep_paid: float = 0.0) -> float:
    """Profit from: recruit units after the tick, raid, sell units back.
    Positive means the 'recruit, raid, sell back' loop is an exploit."""
    return loot - unit_cost * (1 - refund_fraction) - upkeep_paid
