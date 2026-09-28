"""Output bonuses from national projects (the "upgrades"/tech tree).

Shared by the hourly production tick (``app_core.game_ticks.revenue``), the
revenue projection (``countries.get_revenue``) and the province page, so the
number a player is shown is the number the tick pays.

How a building's hourly output is built up (all three places)::

    per_unit * units * (productivity_multiplier + project_bonus)
                     * specialisation * vertical_integration * workforce

The project bonus is *added* to the productivity multiplier, i.e. it is a
percentage of the building's base output, not a multiplier on top of
productivity. Example: productivity 100% (x1.45) + Integrated Steelmaking
(+0.36) = x1.81 of base, not 1.45 * 1.36 = x1.97.
"""

from __future__ import annotations

from typing import Mapping

# building -> (legacy upgrade key, additive share of base output)
PROJECT_OUTPUT_BONUSES: dict[str, tuple[str, float]] = {
    "bauxite_mines": ("strongerexplosives", 0.45),
    "farms": ("advancedmachinery", 0.5),
    "steel_mills": ("integratedsteelmaking", 0.36),
}


def project_output_bonus(building: str, upgrades: Mapping[str, bool]) -> float:
    """Additive output bonus (share of base output) from national projects."""
    entry = PROJECT_OUTPUT_BONUSES.get(building)
    if entry and upgrades.get(entry[0]):
        return entry[1]
    return 0.0
