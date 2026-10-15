"""Pure (no DB) sizing rules for bot nations: names, armies, treasuries.

A bot is sized from the human it is spawned for, so its population places it
inside that player's war range. Military composition affects combat only;
stockpiles scale with province count and difficulty tier.
"""

from __future__ import annotations

import random
from typing import Dict, Iterable, Optional

from wars.war_range import UNIT_WEIGHTS, in_war_range as strength_in_range

BOTS_PER_PLAYER = 3
MAX_BOTS = 300

# War-strength ratio of a bot to the player it was spawned for. The legal
# window is 0.75-1.33x; these keep a margin so a bot that has just lost units
# is still declarable until its next refill.
TIERS = {
    "weak": {"ratio": 0.88, "loot_mult": 1.0},
    "even": {"ratio": 1.0, "loot_mult": 1.3},
    "strong": {"ratio": 1.18, "loot_mult": 1.8},
}
TIER_ORDER = ("weak", "even", "strong")


def tier_for_ratio(ratio: float) -> str:
    if ratio < 0.94:
        return "weak"
    if ratio < 1.09:
        return "even"
    return "strong"


# Share of a bot's *army strength* per unit type, per archetype. Every
# archetype keeps a floor in all three domains so a bot can defend any attack.
ARCHETYPES: Dict[str, Dict[str, float]] = {
    "Garrison State": {
        "soldiers": 0.12,
        "tanks": 0.26,
        "artillery": 0.22,
        "fighters": 0.08,
        "bombers": 0.06,
        "apaches": 0.08,
        "destroyers": 0.06,
        "cruisers": 0.06,
        "submarines": 0.06,
    },
    "Sea Power": {
        "soldiers": 0.05,
        "tanks": 0.08,
        "artillery": 0.07,
        "fighters": 0.08,
        "bombers": 0.08,
        "apaches": 0.06,
        "destroyers": 0.20,
        "cruisers": 0.20,
        "submarines": 0.18,
    },
    "Air Power": {
        "soldiers": 0.05,
        "tanks": 0.08,
        "artillery": 0.07,
        "fighters": 0.22,
        "bombers": 0.22,
        "apaches": 0.16,
        "destroyers": 0.07,
        "cruisers": 0.07,
        "submarines": 0.06,
    },
    "Balanced": {
        "soldiers": 0.08,
        "tanks": 0.14,
        "artillery": 0.12,
        "fighters": 0.14,
        "bombers": 0.12,
        "apaches": 0.10,
        "destroyers": 0.10,
        "cruisers": 0.10,
        "submarines": 0.10,
    },
}

COMBAT_UNITS = tuple(ARCHETYPES["Balanced"].keys())

# Resources a unit's upkeep needs: kept above a floor at all times so bot
# units never go "unusable" mid-war. Everything else regenerates slowly.
UPKEEP_RESOURCES = ("ammunition", "gasoline", "steel", "aluminium", "components", "oil")
UPKEEP_FLOOR_FRACTION = 0.3

# Stock per province (units of each resource), before the tier loot multiplier.
RESOURCE_PER_PROVINCE_DEFAULT = 400_000
RESOURCE_PER_PROVINCE = {
    "rations": 900_000,
    "consumer_goods": 500_000,
    "uranium": 60_000,
    "ammunition": 300_000,
    "gasoline": 250_000,
}
GOLD_PER_PROVINCE = 300_000_000
MIN_GOLD = 600_000_000

# Hourly share of the gap to target that a bot regains (armies, gold, stock).
REGEN_FRACTION = 0.15

_GOVERNMENTS = (
    "Republic of",
    "Kingdom of",
    "Federation of",
    "Commonwealth of",
    "Dominion of",
    "Union of",
    "Principality of",
    "Empire of",
)
_PLACES = (
    "Valdoria",
    "Karnak",
    "Orsova",
    "Tarvos",
    "Meridia",
    "Zelenia",
    "Brannock",
    "Askaria",
    "Velmora",
    "Dravenia",
    "Korvath",
    "Lissandra",
    "Narvik",
    "Olmeria",
    "Pelagia",
    "Quorin",
    "Rhovania",
    "Sundar",
    "Thessaly",
    "Ulmar",
    "Vostrel",
    "Wyndham",
    "Xanthe",
    "Yarrow",
    "Zamora",
    "Ardennia",
    "Belmar",
    "Caldoria",
    "Danubia",
    "Estoria",
    "Fenwick",
    "Galdor",
    "Halvard",
    "Istria",
    "Jorvik",
    "Kestrel",
    "Lorrain",
    "Marrow",
    "Norland",
    "Oberon",
)
BOT_SUFFIX = " [AI]"


def pick_name(index: int, taken: Iterable[str] = ()) -> str:
    """Deterministic, unique, clearly-labelled nation name for bot #index."""
    taken_l = {t.lower() for t in taken}
    n = len(_PLACES)
    for bump in range(0, n * len(_GOVERNMENTS) * 4):
        i = index + bump
        gov = _GOVERNMENTS[(i // n) % len(_GOVERNMENTS)]
        place = _PLACES[i % n]
        generation = i // (n * len(_GOVERNMENTS))
        roman = ("", " II", " III", " IV")[min(generation, 3)]
        name = f"{gov} {place}{roman}{BOT_SUFFIX}"
        if name.lower() not in taken_l:
            return name
    return f"Nation {index}{BOT_SUFFIX}"


def pick_archetype(rng: Optional[random.Random] = None) -> str:
    rng = rng or random
    return rng.choice(sorted(ARCHETYPES))


def resource_target(resource: str, provinces: int, tier: str) -> int:
    base = RESOURCE_PER_PROVINCE.get(resource, RESOURCE_PER_PROVINCE_DEFAULT)
    mult = TIERS.get(tier, TIERS["even"])["loot_mult"]
    return int(base * max(1, provinces) * mult)


def gold_target(provinces: int, tier: str) -> int:
    mult = TIERS.get(tier, TIERS["even"])["loot_mult"]
    return int(max(MIN_GOLD, GOLD_PER_PROVINCE * max(1, provinces)) * mult)


def army_for_strength(archetype: str, army_strength: float) -> Dict[str, int]:
    """Unit counts whose war strength adds up to ``army_strength``."""
    mix = ARCHETYPES.get(archetype) or ARCHETYPES["Balanced"]
    points = max(0.0, float(army_strength))
    # At least one of every unit so a bot can answer an attack in any domain.
    return {
        unit: max(1, int(points * share / UNIT_WEIGHTS[unit]))
        for unit, share in mix.items()
    }


def army_share_of(strength: float, army_strength: float) -> float:
    """Army combat strength as a share of population score, clamped so bots
    don't mirror pure-population or pure-army nations too literally."""
    if strength <= 0:
        return MIN_ARMY_SHARE
    return min(MAX_ARMY_SHARE, max(MIN_ARMY_SHARE, army_strength / strength))


MIN_ARMY_SHARE = 0.15
MAX_ARMY_SHARE = 0.70


def size_bot(
    *,
    provinces: int,
    target_strength: float,
    army_share: float,
    archetype: str,
    tier: str,
    resource_names: Iterable[str],
) -> dict:
    """Full target state (population, gold, stock, army) for a bot nation.

    Target strength is population/1000. Army share determines military
    composition independently of war-range strength.
    """
    provinces = max(1, int(provinces))
    army_share = min(MAX_ARMY_SHARE, max(MIN_ARMY_SHARE, float(army_share)))
    target_strength = max(1.0, float(target_strength))
    population = int(target_strength * 1000.0)
    army_strength = target_strength * army_share / (1.0 - army_share)
    units = army_for_strength(archetype, army_strength)
    return {
        "provinces": provinces,
        "population_per_province": max(1, population // provinces),
        "gold": gold_target(provinces, tier),
        "stock": {r: resource_target(r, provinces, tier) for r in resource_names},
        "units": units,
        "target_strength": int(population / 1000.0),
    }


def regen_toward(
    current: float, target: float, fraction: float = REGEN_FRACTION
) -> int:
    """One regeneration step: close ``fraction`` of the gap (never overshoot)."""
    current, target = float(current or 0), float(target or 0)
    if current >= target:
        return int(current)
    return int(min(target, current + max(1.0, (target - current) * fraction)))


def upkeep_floor(resource: str, target: float) -> float:
    return target * UPKEEP_FLOOR_FRACTION if resource in UPKEEP_RESOURCES else 0.0


def in_war_range(human_strength: float, bot_strength: float) -> bool:
    """True if the human may declare on (and find) the bot: the game's own rule."""
    return strength_in_range(float(human_strength), float(bot_strength))


def missing_tiers(covering: Iterable[tuple], need: int = BOTS_PER_PLAYER) -> list:
    """Tiers to spawn so a human has ``need`` bots in range.

    ``covering`` is (bot_strength, human_strength) for every bot already in
    range. Missing tiers are filled first so the player gets a spread of
    difficulty; once all tiers exist the remainder repeats 'even'.
    """
    covering = list(covering)
    have = [tier_for_ratio((b / h) if h else 1.0) for b, h in covering]
    deficit = need - len(covering)
    out = []
    for tier in TIER_ORDER:
        if deficit <= 0:
            break
        if tier not in have:
            out.append(tier)
            deficit -= 1
    while deficit > 0:
        out.append("even")
        deficit -= 1
    return out
