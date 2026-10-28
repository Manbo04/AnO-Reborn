"""Economies of scale and vertical integration for resource-producing buildings.

Player suggestion 2026-09-25 (luciuskonst, "Economy tweaks/ideas laundry list" #7):

* **Specialisation (economies of scale)** -- the bigger the share of a
  province's slots given over to one producing building type, the more every
  building of that type in the province produces. The curve has diminishing
  returns (``max * (1 - e^(-k * share))``), so the first buildings matter
  most and the bonus flattens out towards ``SCALE_MAX_BONUS``.
* **Vertical integration** -- a processing building (steel mill, refinery,
  factory) gets extra output when its own *province* mines/produces the
  inputs, in proportion to how self-sufficient the province is in the
  scarcest input. Supply is what the province's producers really make per
  hour (productivity, national projects, specialisation, workforce), not
  their base rate; otherwise a province with 2x-boosted mines reads ~half
  self-sufficient while producing a surplus (Andy, 2026-10-27).

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
from app_core.economy.project_bonuses import project_output_bonus

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


def producer_output_multipliers(
    counts: Mapping[str, int],
    land: int,
    city_count: int,
    productivity: float | None,
    upgrades: Mapping[str, bool],
    efficiency_multiplier: float = 1.0,
) -> dict[str, float]:
    """Real output multiplier of every producing building in one province.

    Mirrors the production tick (``plus_amount_multiplier``): (productivity +
    national-project bonus) x specialisation x workforce efficiency. The
    integration bonus itself is left out on purpose -- it is derived from
    these numbers, so including it would be circular.
    """
    if productivity is None:
        productivity_multiplier = 1.0
    else:
        productivity_multiplier = 1.0 + (
            (productivity - 50) * variables.DEFAULT_PRODUCTIVITY_PRODUCTION_MULTIPLIER
        )
    out: dict[str, float] = {}
    for building in SCALE_BUILDINGS:
        if not counts.get(building):
            continue
        scale = scale_bonus(
            counts.get(building, 0) or 0,
            province_slots_for(building, land, city_count),
        )
        out[building] = (
            (productivity_multiplier + project_output_bonus(building, upgrades))
            * (1.0 + scale)
            * efficiency_multiplier
        )
    return out


def self_sufficiency(
    building: str,
    local_counts: Mapping[str, int],
    output_multipliers: Mapping[str, float] | None = None,
) -> float:
    """How much of a processing building's inputs its province produces itself.

    For each input, the province's real hourly output of it (producer count x
    base rate x ``output_multipliers``, which default to 1.0 = base rate) is
    compared with what the province's buildings of this type consume. The
    scarcest input sets the ratio (0..1).
    """
    mult = output_multipliers or {}
    minus = _infra(building).get("minus") or {}
    own = local_counts.get(building, 0) or 0
    if not minus or own <= 0:
        return 0.0
    producers = _producers_by_resource()
    ratios = []
    for resource, per_unit in minus.items():
        demand = own * float(per_unit)
        if demand <= 0:
            continue
        supply = sum(
            (local_counts.get(b, 0) or 0) * amount * mult.get(b, 1.0)
            for b, amount in producers.get(resource, ())
        )
        ratios.append(min(1.0, supply / demand))
    return min(ratios) if ratios else 0.0


def integration_bonus(
    building: str,
    local_counts: Mapping[str, int],
    output_multipliers: Mapping[str, float] | None = None,
) -> float:
    """Vertical-integration bonus (0..INTEGRATION_MAX_BONUS)."""
    if building not in PROCESSING_BUILDINGS:
        return 0.0
    return INTEGRATION_MAX_BONUS * self_sufficiency(
        building, local_counts, output_multipliers
    )


def province_slots_for(building: str, land: int, city_count: int) -> int:
    """The province slot pool a building type competes for."""
    return int(city_count or 0) if building in CITY_UNITS else int(land or 0)


def production_bonuses(
    building: str,
    province_counts: Mapping[str, int],
    land: int,
    city_count: int,
    nation_counts: Mapping[str, int] = None,
    output_multipliers: Mapping[str, float] = None,
) -> dict:
    """Both bonuses for one building type in one province.

    ``nation_counts`` is accepted for call-site compatibility but unused:
    integration is a per-province bonus (Oct 3 design change). Pass
    ``output_multipliers`` (see ``producer_output_multipliers``) so supply is
    measured at real output rather than base rates.

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
    integration = integration_bonus(building, province_counts, output_multipliers)
    return {
        "scale": scale,
        "integration": integration,
        "multiplier": (1.0 + scale) * (1.0 + integration),
    }
