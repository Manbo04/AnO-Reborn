"""Canonical per-biome raw-material building availability.

Single source of truth extracted from the classic province page's buy
section (the actively-maintained, functional mapping — the summary table
at the top of that page had drifted from it for Jungle) so classic view,
base view, and server-side purchase validation share one definition and
can't drift apart again.
"""

from __future__ import annotations

ALL_MINE_BUILDINGS: tuple[str, ...] = (
    "coal_mines",
    "iron_mines",
    "copper_mines",
    "bauxite_mines",
    "lead_mines",
    "uranium_mines",
    "pumpjacks",
    "lumber_mills",
)

BIOME_MINES: dict[str, tuple[str, ...]] = {
    "tundra": ("iron_mines", "copper_mines", "lead_mines", "uranium_mines"),
    "desert": ("iron_mines", "pumpjacks", "bauxite_mines", "uranium_mines"),
    "boreal forest": ("iron_mines", "lumber_mills", "lead_mines", "coal_mines"),
    "grassland": ("iron_mines", "copper_mines", "bauxite_mines", "pumpjacks"),
    "savanna": ("coal_mines", "copper_mines", "lead_mines", "bauxite_mines"),
    "mountain range": ("coal_mines", "pumpjacks", "bauxite_mines", "lumber_mills"),
    "jungle": ("coal_mines", "copper_mines", "lumber_mills", "pumpjacks"),
}


def mines_for_biome(location: str | None) -> tuple[str, ...]:
    """Raw-material mine/well types buildable in a given province biome.

    Falls back to the full list for unrecognized location values (a
    handful of legacy accounts carry stale/corrupt `stats.location` data)
    rather than silently blocking every mine purchase for those accounts.
    """
    if not location:
        return ALL_MINE_BUILDINGS
    return BIOME_MINES.get(location.strip().lower(), ALL_MINE_BUILDINGS)


def is_mine_allowed_in_biome(building_name: str, location: str | None) -> bool:
    if building_name not in ALL_MINE_BUILDINGS:
        return True  # not a biome-restricted building type
    return building_name in mines_for_biome(location)
