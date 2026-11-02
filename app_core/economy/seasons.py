"""Real-calendar seasons for a nation's biome.

No timer and no stored "current season". The date (UTC) picks the
meteorological season, the nation's existing ``stats.location`` biome picks
the climate and which hemisphere that climate sits in, and one table below
turns that pair into small multipliers. The hourly economy ticks and the
pages that preview them read this module, so the numbers stay in one place.

Tune balance by editing ``EFFECTS``. 1.0 / 0 means no change.

Meteorological seasons (northern hemisphere):
    Mar–May spring, Jun–Aug summer, Sep–Nov autumn, Dec–Feb winter.
Southern-hemisphere biomes use the opposite season. Tropical climates keep
the same four slots but show them as wet/dry seasons.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

# Farms and fisheries are the food producers the revenue tick already pays.
FOOD_BUILDINGS = frozenset({"farms", "fisheries"})

SEASONS = ("spring", "summer", "autumn", "winter")

SEASON_LABELS = {
    "spring": "Spring",
    "summer": "Summer",
    "autumn": "Autumn",
    "winter": "Winter",
}

# Tropical biomes don't have a temperate spring. Same four slots, local names.
TROPICAL_LABELS = {
    "spring": "Early rains",
    "summer": "Wet season",
    "autumn": "Late rains",
    "winter": "Dry season",
}

OPPOSITE = {
    "spring": "autumn",
    "autumn": "spring",
    "summer": "winter",
    "winter": "summer",
}

# Next meteorological boundary, in month order. The calendar dates are the
# same in both hemispheres; only the season name flips.
_BOUNDARIES = (3, 6, 9, 12)

# ``stats.location`` values (see CANONICAL_BIOMES). There is no latitude
# column. Climate is the family the effect table uses. Hemisphere defaults
# to north because these names are climate belts, not countries.
# Savanna is the southern-hemisphere tropical belt (southern Africa and
# Australia): its wet season is the southern summer, Dec–Feb. Jungle stays
# on the northern wet season (Jun–Aug). Anything unrecognised, including a
# missing location, is temperate and northern — the same fallback the rest
# of the game uses for Grassland.
BIOME_PROFILE: dict[str, tuple[str, str]] = {
    "tundra": ("arctic", "north"),
    "boreal forest": ("arctic", "north"),
    "grassland": ("temperate", "north"),
    "mountain range": ("temperate", "north"),
    "desert": ("desert", "north"),
    "jungle": ("tropical", "north"),
    "savanna": ("tropical", "south"),
}

CLIMATE_LABELS = {
    "temperate": "Temperate",
    "tropical": "Tropical",
    "desert": "Desert",
    "arctic": "Arctic",
    "mediterranean": "Mediterranean",
}

_ICONS = {
    "spring": "local_florist",
    "summer": "wb_sunny",
    "autumn": "park",
    "winter": "ac_unit",
}

_TROPICAL_ICONS = {
    "spring": "grain",
    "summer": "water_drop",
    "autumn": "water_drop",
    "winter": "wb_sunny",
}


@dataclass(frozen=True)
class SeasonEffects:
    """Multipliers are applied to existing formulas. 1.0 leaves them alone.

    ``happiness`` is a mood shift for births and settlers only. It is not
    written onto the province happiness bar (that bar already stacks every
    hour from buildings, so a seasonal ±1 would pin it at 0 or 100).
    ``construction`` scales building gold upkeep. It stays at 1.0: buildings
    are bought instantly, so there is no construction timer to slow down.
    """

    food: float = 1.0
    energy: float = 1.0
    growth: float = 1.0
    happiness: int = 0
    defense: float = 1.0
    construction: float = 1.0


def _fx(
    food: float = 1.0,
    energy: float = 1.0,
    growth: float = 1.0,
    happiness: int = 0,
    defense: float = 1.0,
    construction: float = 1.0,
) -> SeasonEffects:
    return SeasonEffects(food, energy, growth, happiness, defense, construction)


# climate -> season -> effects. Keep these close to 1. A new climate is one
# row; a new season is one key. Missing pairs fall back to no change.
EFFECTS: dict[str, dict[str, SeasonEffects]] = {
    "temperate": {
        "spring": _fx(food=1.06, growth=1.02, happiness=1),
        "summer": _fx(food=1.04, energy=1.03, growth=1.01, happiness=1),
        "autumn": _fx(food=1.03, energy=1.02),
        "winter": _fx(food=0.94, energy=1.06, growth=0.98, happiness=-1),
    },
    "mediterranean": {
        "spring": _fx(food=1.05, growth=1.02, happiness=1),
        "summer": _fx(food=0.96, energy=1.04, growth=0.99),
        "autumn": _fx(food=1.03, growth=1.01),
        "winter": _fx(food=1.04, energy=1.02, growth=1.01),
    },
    "tropical": {
        "spring": _fx(food=1.03, energy=1.01, growth=1.01),
        "summer": _fx(food=1.06, energy=1.02, growth=1.02, happiness=1),
        "autumn": _fx(food=1.02, energy=1.01),
        "winter": _fx(food=0.94, growth=0.98, happiness=-1),
    },
    "desert": {
        "spring": _fx(food=1.04, growth=1.01),
        "summer": _fx(food=0.90, energy=1.08, growth=0.97, happiness=-1),
        "autumn": _fx(food=1.02, energy=1.02),
        "winter": _fx(food=1.05, growth=1.02, happiness=1),
    },
    "arctic": {
        "spring": _fx(food=0.97, energy=1.04, growth=0.99),
        "summer": _fx(food=1.08, growth=1.03, happiness=1),
        "autumn": _fx(food=0.95, energy=1.05, growth=0.98, happiness=-1),
        "winter": _fx(food=0.86, energy=1.10, growth=0.96, happiness=-2, defense=1.08),
    },
}

_NEUTRAL = SeasonEffects()


def utc_today(when: datetime.date | datetime.datetime | None = None) -> datetime.date:
    """Season boundaries are UTC dates, same clock as the economy ticks."""
    if when is None:
        return datetime.datetime.now(datetime.timezone.utc).date()
    if isinstance(when, datetime.datetime):
        if when.tzinfo is None:
            when = when.replace(tzinfo=datetime.timezone.utc)
        return when.astimezone(datetime.timezone.utc).date()
    return when


def northern_season(month: int) -> str:
    """Meteorological season for a calendar month, northern hemisphere."""
    if month in (3, 4, 5):
        return "spring"
    if month in (6, 7, 8):
        return "summer"
    if month in (9, 10, 11):
        return "autumn"
    return "winter"


def local_season(when: datetime.date, hemisphere: str) -> str:
    """Season name after the hemisphere flip. South is the opposite season."""
    season = northern_season(when.month)
    if (hemisphere or "north").strip().lower() == "south":
        return OPPOSITE[season]
    return season


def days_until_next_season(when: datetime.date | None = None) -> int:
    """Whole days until the next meteorological boundary (1 Mar/Jun/Sep/Dec).

    On the boundary day itself the new season has started, so this counts
    forward to the one after that. Always at least 1 (tomorrow, on the last
    day of a season) and at most the length of the current season.
    """
    today = utc_today(when)
    year = today.year
    candidates = [datetime.date(year, month, 1) for month in _BOUNDARIES]
    candidates.append(datetime.date(year + 1, 3, 1))
    for boundary in candidates:
        if boundary > today:
            return (boundary - today).days
    return (candidates[-1] - today).days


def next_season_key(season: str) -> str:
    idx = SEASONS.index(season) if season in SEASONS else 0
    return SEASONS[(idx + 1) % len(SEASONS)]


def biome_profile(location: str | None) -> tuple[str, str]:
    """(climate, hemisphere) for a ``stats.location`` value.

    Unknown or empty locations are temperate / north.
    """
    if not isinstance(location, str):
        return ("temperate", "north")
    key = location.strip().lower()
    if not key:
        return ("temperate", "north")
    return BIOME_PROFILE.get(key, ("temperate", "north"))


def effects_for(climate: str, season: str) -> SeasonEffects:
    """Table lookup. Unknown climate or season is no change."""
    return EFFECTS.get(climate, {}).get(season, _NEUTRAL)


def _known_location(location: str | None) -> str | None:
    """A real biome string. Missing values mean 'caller has no biome yet'
    and must not invent a seasonal penalty (tests and half-loaded rows)."""
    if not isinstance(location, str):
        return None
    text = location.strip()
    return text or None


def _label_for(climate: str, season: str) -> str:
    if climate == "tropical":
        return TROPICAL_LABELS.get(season, SEASON_LABELS.get(season, season.title()))
    return SEASON_LABELS.get(season, season.title())


def _icon_for(climate: str, season: str) -> str:
    if climate == "tropical":
        return _TROPICAL_ICONS.get(season, "public")
    return _ICONS.get(season, "public")


def visual_kind(climate: str, season: str) -> str:
    """CSS ambience key. ``none`` draws nothing.

    Snow only where winter is actually cold. Tropical wet months get a few
    rain streaks; the dry season gets faint dust. Summer elsewhere is a
    warm glow with no particles.
    """
    if season == "summer" and climate != "tropical":
        return "glow"
    if season == "winter" and climate in ("arctic", "temperate"):
        return "snow"
    if season == "autumn" and climate in ("temperate", "mediterranean", "arctic"):
        return "leaves"
    if season == "spring" and climate in ("temperate", "mediterranean", "arctic"):
        return "petals"
    if climate == "tropical" and season in ("spring", "summer", "autumn"):
        return "rain"
    if climate == "tropical" and season == "winter":
        return "dust"
    if climate == "desert" and season == "summer":
        return "glow"
    return "none"


def _pct(multiplier: float) -> str:
    points = int(round((multiplier - 1.0) * 100))
    if points > 0:
        return f"+{points}%"
    return f"{points}%"


def effect_lines(fx: SeasonEffects) -> tuple[str, ...]:
    """Plain-language lines for the badge tooltip. Neutral knobs are omitted."""
    lines: list[str] = []
    if fx.food != 1.0:
        lines.append(f"Farms and fisheries {_pct(fx.food)}")
    if fx.energy != 1.0:
        lines.append(f"Power use {_pct(fx.energy)}")
    if fx.growth != 1.0:
        lines.append(f"Population growth {_pct(fx.growth)}")
    if fx.happiness > 0:
        lines.append("Mood: a little better (more births, not the happiness bar)")
    elif fx.happiness < 0:
        lines.append("Mood: a little worse (fewer births, not the happiness bar)")
    if fx.defense != 1.0:
        lines.append(f"Ground defense {_pct(fx.defense)}")
    if fx.construction != 1.0:
        lines.append(f"Building upkeep {_pct(fx.construction)}")
    if not lines:
        lines.append("No strong seasonal shift this month")
    return tuple(lines)


def biome_label(location: str | None) -> str:
    if not isinstance(location, str) or not location.strip():
        return "Grassland"
    return " ".join(part.capitalize() for part in location.strip().split())


@dataclass(frozen=True)
class SeasonSnapshot:
    """Everything the badge, the ticks, and the battle modifier need."""

    season: str
    label: str
    next_label: str
    days_left: int
    days_phrase: str
    climate: str
    climate_label: str
    hemisphere: str
    hemisphere_label: str
    biome: str
    lines: tuple[str, ...]
    visual: str
    icon: str
    food: float
    energy: float
    growth: float
    happiness: int
    defense: float
    construction: float

    @property
    def summary(self) -> str:
        return f"{self.label} · {self.days_phrase} until {self.next_label}"


def season_snapshot(
    location: str | None,
    when: datetime.date | datetime.datetime | None = None,
    hemisphere: str | None = None,
) -> SeasonSnapshot:
    """Full description for one biome on one date.

    ``hemisphere`` overrides the biome's mapped hemisphere (tests, and any
    future column). Omit it to use ``BIOME_PROFILE``.
    """
    today = utc_today(when)
    climate, mapped_hemisphere = biome_profile(location)
    hemi = (hemisphere or mapped_hemisphere or "north").strip().lower()
    if hemi not in ("north", "south"):
        hemi = "north"
    season = local_season(today, hemi)
    fx = effects_for(climate, season)
    nxt = next_season_key(season)
    days = days_until_next_season(today)
    day_word = "day" if days == 1 else "days"
    return SeasonSnapshot(
        season=season,
        label=_label_for(climate, season),
        next_label=_label_for(climate, nxt),
        days_left=days,
        days_phrase=f"{days} {day_word}",
        climate=climate,
        climate_label=CLIMATE_LABELS.get(climate, climate.title()),
        hemisphere=hemi,
        hemisphere_label=(
            "Southern hemisphere" if hemi == "south" else "Northern hemisphere"
        ),
        biome=biome_label(location),
        lines=effect_lines(fx),
        visual=visual_kind(climate, season),
        icon=_icon_for(climate, season),
        food=fx.food,
        energy=fx.energy,
        growth=fx.growth,
        happiness=fx.happiness,
        defense=fx.defense,
        construction=fx.construction,
    )


def _snapshot_or_neutral(
    location: str | None,
    when: datetime.date | datetime.datetime | None = None,
) -> SeasonSnapshot | None:
    if _known_location(location) is None:
        return None
    return season_snapshot(location, when)


def food_output_multiplier(
    building: str,
    location: str | None,
    when: datetime.date | datetime.datetime | None = None,
) -> float:
    """Output multiplier for one producing building. Non-food buildings are 1."""
    if building not in FOOD_BUILDINGS:
        return 1.0
    snap = _snapshot_or_neutral(location, when)
    if snap is None:
        return 1.0
    return snap.food


def energy_upkeep_multiplier(
    location: str | None,
    when: datetime.date | datetime.datetime | None = None,
) -> float:
    """Heating / cooling multiplier on energy consumed by running buildings."""
    snap = _snapshot_or_neutral(location, when)
    if snap is None:
        return 1.0
    return snap.energy


def growth_multiplier(
    location: str | None,
    when: datetime.date | datetime.datetime | None = None,
) -> float:
    """Multiplier on births, settlers, and the legacy nation-growth formula."""
    snap = _snapshot_or_neutral(location, when)
    if snap is None:
        return 1.0
    return snap.growth


def mood_bonus(
    location: str | None,
    when: datetime.date | datetime.datetime | None = None,
) -> int:
    """Happiness points added only inside the birth/settler formula."""
    snap = _snapshot_or_neutral(location, when)
    if snap is None:
        return 0
    return snap.happiness


def defense_multiplier(
    location: str | None,
    when: datetime.date | datetime.datetime | None = None,
) -> float:
    """Ground-defense multiplier. Only arctic winter is above 1 today."""
    snap = _snapshot_or_neutral(location, when)
    if snap is None:
        return 1.0
    return snap.defense


def construction_multiplier(
    location: str | None,
    when: datetime.date | datetime.datetime | None = None,
) -> float:
    """Gold upkeep multiplier. The table currently leaves this at 1."""
    snap = _snapshot_or_neutral(location, when)
    if snap is None:
        return 1.0
    return snap.construction
