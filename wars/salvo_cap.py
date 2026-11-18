"""Civilian damage cap for one Fire All salvo (flag ``nuke_salvo_civilian_cap``).

Problem (Dede, 2026-11): a single nuke is not the problem, MANY at once are. A Fire
All salvo lands one warhead per enemy province and each one also adds nation-wide
fallout, so a full salvo against a small or mid-sized nation can wipe most of its
people and buildings in one click.

Rule (flag ON): ONE salvo may kill at most SALVO_CIVILIAN_CAP_DEATHS of the target
nation's people and destroy at most SALVO_CIVILIAN_CAP_BUILDINGS of its buildings (and
SALVO_CIVILIAN_CAP_CITIES of its cities), measured against the totals BEFORE the first
warhead. Deaths include the fallout deaths that every warhead adds across the nation.

* A single warhead is never weakened. The first warhead that gets through is applied
  in full, and the cap for each measure is ``max(cap, damage of that first warhead)``.
  A one-warhead salvo therefore does exactly what it does today.
* Interception happens before any of this: an intercepted warhead did nothing, so it
  counts for nothing.
* A warhead that would be cut to zero is not fired: it stays in the stockpile and
  costs nothing. A warhead that is only partly cut is fired and spent; its damage is
  reduced so the running total lands exactly on the cap.
* Applies to retaliation and automatic retaliation salvos (they all use execute_salvo).

Everything here is pure (no database) so the math is unit tested. The DB side is in
wars/nuclear.py (``execute_strike(..., salvo_cap=...)``) and wars/nuclear_salvo.py.
Rollback: switch the flag off at /admin/flags; the old behaviour returns at once.
"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Iterable, List, Optional

from app_core.feature_flags import is_on

FLAG = "nuke_salvo_civilian_cap"

# --- Tunable numbers (the only place they live) -------------------------------------
SALVO_CIVILIAN_CAP_DEATHS = 0.25  # share of the nation's people one salvo may kill
SALVO_CIVILIAN_CAP_BUILDINGS = (
    0.25  # share of the nation's buildings one salvo may destroy
)
SALVO_CIVILIAN_CAP_CITIES = 0.25  # share of the nation's cities one salvo may destroy
# ---------------------------------------------------------------------------------


def enabled(user_id=None) -> bool:
    """True when the salvo cap is on. A flag read never raises: unreadable = off."""
    try:
        return is_on(FLAG, user_id)
    except Exception:
        return False


def _cap_amount(total: int, frac: float) -> int:
    return int(math.floor(max(0, int(total or 0)) * float(frac)))


class SalvoCap:
    """Running totals for ONE salvo against ONE nation.

    ``remaining()`` says how much more of each measure the next warhead may do; ``None``
    means "no limit yet" (nothing has landed, so the first warhead is never weakened).
    """

    MEASURES = ("deaths", "buildings", "cities")

    def __init__(
        self,
        pop_total: int,
        buildings_total: int,
        cities_total: int,
        frac_deaths: float = SALVO_CIVILIAN_CAP_DEATHS,
        frac_buildings: float = SALVO_CIVILIAN_CAP_BUILDINGS,
        frac_cities: float = SALVO_CIVILIAN_CAP_CITIES,
    ):
        self.totals = {
            "deaths": int(pop_total or 0),
            "buildings": int(buildings_total or 0),
            "cities": int(cities_total or 0),
        }
        self.cap = {
            "deaths": _cap_amount(pop_total, frac_deaths),
            "buildings": _cap_amount(buildings_total, frac_buildings),
            "cities": _cap_amount(cities_total, frac_cities),
        }
        self.used = {m: 0 for m in self.MEASURES}
        self.landed = 0  # warheads that got through and did something

    def remaining(self) -> dict:
        if self.landed == 0:
            return {m: None for m in self.MEASURES}
        return {m: max(0, self.cap[m] - self.used[m]) for m in self.MEASURES}

    def exhausted(self) -> bool:
        """True when no measure has room left (a further warhead would do nothing)."""
        if self.landed == 0:
            return False
        return all(v == 0 for v in self.remaining().values())

    def record(self, deaths: int, buildings: int, cities: int) -> None:
        """Add one warhead that landed. The first one lifts the cap to its own damage
        when that is higher (a single warhead is never weakened)."""
        self.used["deaths"] += max(0, int(deaths))
        self.used["buildings"] += max(0, int(buildings))
        self.used["cities"] += max(0, int(cities))
        self.landed += 1
        if self.landed == 1:
            for m in self.MEASURES:
                self.cap[m] = max(self.cap[m], self.used[m])


def clamp(requested: int, remaining: Optional[int]) -> int:
    """Damage the warhead may actually do: all of it, or what is left under the cap."""
    requested = max(0, int(requested))
    if remaining is None:
        return requested
    return min(requested, max(0, int(remaining)))


def fallout_deaths(populations: Iterable[int], pct: float) -> int:
    """People radiation kills when it takes ``pct`` of every province's population.
    Mirrors wars.aftermath.kill_civilians (FLOOR per province, exact decimal maths)."""
    p = Decimal(repr(float(pct)))
    return int(
        sum(
            int((Decimal(int(pop)) * p).to_integral_value(rounding="ROUND_FLOOR"))
            for pop in populations
            if int(pop) > 0
        )
    )


def fallout_pct_for_allowance(
    populations: Iterable[int], pct: float, allowed: int
) -> float:
    """Largest fallout percentage <= ``pct`` whose deaths do not exceed ``allowed``."""
    pops: List[int] = [int(p) for p in populations]
    if allowed is None or fallout_deaths(pops, pct) <= allowed:
        return pct
    if allowed <= 0:
        return 0.0
    lo, hi = 0.0, float(pct)
    for _ in range(60):  # deaths only go up as pct goes up, so bisect
        mid = (lo + hi) / 2.0
        if fallout_deaths(pops, mid) <= allowed:
            lo = mid
        else:
            hi = mid
    return lo


def allocate_building_losses(
    quantities: List[int], frac: float, allowed: Optional[int]
) -> List[int]:
    """Per-building-type losses for one province: ``floor(quantity * frac)`` each (what
    the unlimited strike destroys), trimmed so the total never exceeds ``allowed``.
    Trimming is proportional, the leftover goes to the largest remainders."""
    wanted = [max(0, int(math.floor(max(0, int(q)) * float(frac)))) for q in quantities]
    total = sum(wanted)
    if allowed is None or total <= allowed:
        return wanted
    allowed = max(0, int(allowed))
    if allowed == 0 or total == 0:
        return [0] * len(wanted)
    scale = allowed / total
    scaled = [w * scale for w in wanted]
    out = [int(math.floor(s)) for s in scaled]
    spare = allowed - sum(out)
    order = sorted(range(len(wanted)), key=lambda i: (scaled[i] - out[i]), reverse=True)
    for i in order:
        if spare <= 0:
            break
        if out[i] < wanted[i]:
            out[i] += 1
            spare -= 1
    return out
