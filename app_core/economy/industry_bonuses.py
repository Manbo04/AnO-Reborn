"""Economies of scale and vertical integration for resource-producing buildings.

Player suggestion 2026-09-25 (luciuskonst, "Economy tweaks/ideas laundry list" #7):

* **Specialisation (economies of scale)** -- the bigger the share of a
  province's slots given over to one producing building type, the more every
  building of that type in the province produces. The curve has diminishing
  returns (``max * (1 - e^(-k * share))``), so the first buildings matter
  most and the bonus flattens out towards ``SCALE_MAX_BONUS``.
* **Vertical integration** -- a processing building (steel mill, refinery,
  factory) gets extra output when the nation mines/produces its own inputs,
  in proportion to how self-sufficient the nation is in the scarcest input.

This is the single implementation used by the hourly production tick
(``app_core.game_ticks.revenue``), the revenue projection (``countries.py``)
and the province page, so the displayed numbers match what the tick pays.
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Mapping

import variables
from app_core.economy.building_costs import CITY_UNITS

# Tunables (kept here next to the formula they tune).
SCALE_MAX_BONUS = 0.15  # asymptotic cap: +15% output
SCALE_CURVE_K = 4.0  # steepness: 25% of slots -> ~+9.5%, 50% -> ~+13%
INTEGRATION_MAX_BONUS = 0.10  # +10% output when fully self-sufficient

# Buildings that produce a stockpiled resource (mines, farms, processing,
# industrial districts). Power plants, retail and civic buildings are left out.
SCALE_BUILDINGS: frozenset[str] = frozenset(
    variables.INFRA_TYPE_BUILDINGS["industry"]
    + variables.INFRA_TYPE_BUILDINGS["processing"]
    + ["industrial_district"]
)
PROCESSING_BUILDINGS: frozenset[str] = frozenset(
    variables.INFRA_TYPE_BUILDINGS["processing"]
)


def _infra(building: str) -> dict:
    return variables.NEW_INFRA.get(building, {})


@lru_cache(maxsize=1)
def _producers_by_resource() -> dict[str, tuple[tuple[str, float], ...]]:
    """resource -> ((building, base output per building), ...)"""
    out: dict[str, list[tuple[str, float]]] = {}
    for building in SCALE_BUILDINGS:
        for resource, amount in (_infra(building).get("plus") or {}).items():
            out.setdefault(resource, []).append((building, float(amount)))
    return {k: tuple(v) for k, v in out.items()}


def scale_bonus(count_in_province: int, province_slots: int) -> float:
    """Specialisation bonus (0..SCALE_MAX_BONUS) for one building type."""
    if count_in_province <= 0 or province_slots <= 0:
        return 0.0
    share = min(1.0, count_in_province / province_slots)
    return SCALE_MAX_BONUS * (1.0 - math.exp(-SCALE_CURVE_K * share))


def self_sufficiency(building: str, nation_counts: Mapping[str, int]) -> float:
    """How much of a processing building's inputs the nation produces itself.

    For each input, domestic output capacity (all producing buildings in the
    nation, base rates) is compared with what the nation's buildings of this
    type consume. The scarcest input sets the ratio (0..1).
    """
    minus = _infra(building).get("minus") or {}
    own = nation_counts.get(building, 0) or 0
    if not minus or own <= 0:
        return 0.0
    producers = _producers_by_resource()
    ratios = []
    for resource, per_unit in minus.items():
        demand = own * float(per_unit)
        if demand <= 0:
            continue
        supply = sum(
            (nation_counts.get(b, 0) or 0) * amount
            for b, amount in producers.get(resource, ())
        )
        ratios.append(min(1.0, supply / demand))
    return min(ratios) if ratios else 0.0


def integration_bonus(building: str, nation_counts: Mapping[str, int]) -> float:
    """Vertical-integration bonus (0..INTEGRATION_MAX_BONUS)."""
    if building not in PROCESSING_BUILDINGS:
        return 0.0
    return INTEGRATION_MAX_BONUS * self_sufficiency(building, nation_counts)


def province_slots_for(building: str, land: int, city_count: int) -> int:
    """The province slot pool a building type competes for."""
    return int(city_count or 0) if building in CITY_UNITS else int(land or 0)


def production_bonuses(
    building: str,
    province_counts: Mapping[str, int],
    land: int,
    city_count: int,
    nation_counts: Mapping[str, int] = None,
) -> dict:
    """Both bonuses for one building type in one province.

    Returns ``{"scale": float, "integration": float, "multiplier": float}``;
    the multiplier is applied to output on top of every other modifier.
    """
    if building not in SCALE_BUILDINGS:
        return {"scale": 0.0, "integration": 0.0, "multiplier": 1.0}
    scale = scale_bonus(
        province_counts.get(building, 0) or 0,
        province_slots_for(building, land, city_count),
    )
    # Vertical integration bonus is calculated per-province based on locally produced inputs
    integration = integration_bonus(building, province_counts)
    return {
        "scale": scale,
        "integration": integration,
        "multiplier": (1.0 + scale) * (1.0 + integration),
    }
