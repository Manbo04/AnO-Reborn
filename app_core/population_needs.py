"""One clear answer to "what does my population need right now?".

Pure function over numbers the nation page already has, so the page, the tests
and any future bot command all read the same rows. Each row says what is
needed, what the nation has, what is missing and what to build.
"""
import math

import variables
from app_core.game_ticks import population2

# (building, people reached) tiers worth suggesting, cheapest first
_DIST_SUGGEST = ("food_banks", "distribution_centers", "malls")


def _row(key, label, unit, need, have, ok, advice="", note=""):
    return {
        "key": key,
        "label": label,
        "unit": unit,
        "need": int(need),
        "have": int(have),
        "missing": int(max(0, need - have)),
        "ok": bool(ok),
        "advice": advice if not ok else "",
        "note": note,
    }


def hospitals_needed(population):
    """Hospitals for 100% cover (mirrors population2.hospital_cover)."""
    pop = max(0, int(population or 0))
    if pop <= 0:
        return 0
    return int(math.ceil(pop / population2.HOSPITAL_CAPACITY))


def build_population_needs(
    population, rations_need, distribution_status, pop2,
):
    pop = int(population or 0)
    rows = []

    ds = distribution_status or {}
    stock = int(ds.get("rations_stockpile") or 0)
    need = int(rations_need or 0)
    if ds:
        hours = stock / need if need else 0
        note = f"stock lasts {hours:,.0f} hours" if need else ""
        rows.append(_row(
            "rations", "Rations eaten per hour", "rations",
            need, stock, stock >= need,
            "Build farms or buy rations so the stockpile covers at least one hour.",
            note,
        ))

        cap = int(ds.get("distribution_cap") or 0)
        eff = (ds.get("efficiency_percent") or 100) / 100
        tiers = []
        missing = max(0, pop - cap)
        for b in _DIST_SUGGEST:
            per = variables.RATIONS_DISTRIBUTION_PER_BUILDING[b] * eff
            if per > 0:
                tiers.append(f"{math.ceil(missing / per):,} {b.replace('_', ' ')}")
        note = (
            f"each building reaches {ds['efficiency_percent']}% of normal (nation is over comfort size)"
            if eff < 1 else ""
        )
        rows.append(_row(
            "distribution", "People reached by distribution", "people",
            pop, cap, cap >= pop,
            "Build " + " or ".join(tiers) + ". Unreached people starve"
            + (" (paused until 19 Oct 18:00 UTC)." if ds.get("starvation_grace") else "."),
            note,
        ))

    if pop2:
        homes = int(pop2.get("homes") or 0)
        short = max(0, pop - homes)
        rows.append(_row(
            "homes", "Homes", "homes", pop, homes, pop <= homes,
            f"Over 100% full slows births, 120% stops them. Build about "
            f"{math.ceil(short / population2.HOMES_PER_DISTRICT):,} districts "
            f"(+{population2.HOMES_PER_DISTRICT:,} homes each) or buy land "
            f"(+{population2.HOMES_PER_LAND:,} each).",
        ))
        need_h = hospitals_needed(pop)
        have_h = int(pop2.get("hospitals") or 0)
        rows.append(_row(
            "hospitals", "Hospitals", "hospitals", need_h, have_h, have_h >= need_h,
            f"Build {need_h - have_h:,} more hospitals to cut deaths to the minimum.",
            f"{pop2.get('hospital_cover_pct', 0):.0f}% of people covered",
        ))

    return {
        "rows": rows,
        "problems": sum(1 for r in rows if not r["ok"]),
        "starvation_grace": bool(ds.get("starvation_grace")),
    }
