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

CANONICAL_BIOMES: tuple[str, ...] = (
    "Tundra",
    "Desert",
    "Boreal Forest",
    "Grassland",
    "Savanna",
    "Mountain Range",
    "Jungle",
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


# Display metadata for the "not available in your biome" cards on the
# classic province page -- lets players see a trade partner's raw-material
# costs/output even for mines they can't build themselves, instead of the
# building simply not existing on the page (player-requested, see
# "City buildings" in #bug-reports).
MINE_INFO: dict[str, dict[str, str]] = {
    "iron_mines": {
        "display_name": "Iron Mines",
        "resource": "iron",
        "description": "Iron mines produce iron which is necessary to produce steel.",
    },
    "coal_mines": {
        "display_name": "Coal Mines",
        "resource": "coal",
        "description": "Coal mines produce coal. Coal can be used to fuel coal power plants, or can be combined with iron to produce steel.",
    },
    "copper_mines": {
        "display_name": "Copper Mines",
        "resource": "copper",
        "description": "Copper mines produce copper for your nation. Copper can be used to manufacture ammunition.",
    },
    "bauxite_mines": {
        "display_name": "Bauxite Mines",
        "resource": "bauxite",
        "description": "Bauxite mines make bauxite for your country. Bauxite can be processed into aluminium.",
    },
    "lead_mines": {
        "display_name": "Lead Mines",
        "resource": "lead",
        "description": "Lead mines allow for the production of lead, which is valuable for its use in ammunition.",
    },
    "uranium_mines": {
        "display_name": "Uranium Mines",
        "resource": "uranium",
        "description": "Uranium mines harvest uranium, which can be used to fuel nuclear reactors, or in nuclear weapons.",
    },
    "pumpjacks": {
        "display_name": "Pumpjacks",
        "resource": "oil",
        "description": "Pumpjacks harvest oil from the ground, providing a resource that can be processed into gasoline.",
    },
    "lumber_mills": {
        "display_name": "Lumber Mills",
        "resource": "lumber",
        "description": "Lumber mills produce lumber, a useful raw resource used to mines and farms.",
    },
}


def other_biome_mines(location: str | None) -> list[dict[str, str]]:
    """Raw-material mines NOT buildable in this biome, for display-only cards."""
    allowed = set(mines_for_biome(location))
    return [
        {"name": name, **MINE_INFO[name]}
        for name in ALL_MINE_BUILDINGS
        if name not in allowed
    ]


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
