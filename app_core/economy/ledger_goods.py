"""Ledger atlas goods: master visibility switch (feature flag ``ledger_goods``).

The 11 goods and their producer buildings exist in the data model (columns,
dictionaries, tick recipes) but stay invisible, unbuildable and untradable
until the flag is on. With the flag off nobody can own a producer building,
so no unit of these goods can ever exist.
"""
from app_core.feature_flags import is_on

FLAG = "ledger_goods"

LEDGER_RESOURCES = (
    "machinery",
    "cement",
    "textiles",
    "clothing",
    "chemicals",
    "medicine",
    "fertilizer",
    "plastics",
    "electronics",
    "vehicles",
    "luxury_goods",
)

LEDGER_BUILDINGS = (
    "machinery_works",
    "cement_works",
    "textile_mills",
    "clothing_factories",
    "chemical_plants",
    "pharmaceutical_labs",
    "fertilizer_plants",
    "plastics_plants",
    "electronics_factories",
    "vehicle_works",
    "luxury_workshops",
)

_HIDDEN = frozenset(LEDGER_RESOURCES) | frozenset(LEDGER_BUILDINGS)


def enabled(user_id=None) -> bool:
    """True when the new goods are switched on (never raises)."""
    return is_on(FLAG, user_id)


def is_hidden(name) -> bool:
    """True when ``name`` is a Ledger good/building and the flag is off."""
    return name in _HIDDEN and not enabled()


def visible(names):
    """``names`` without the Ledger goods/buildings while the flag is off."""
    if enabled():
        return list(names)
    return [n for n in names if n not in _HIDDEN]
