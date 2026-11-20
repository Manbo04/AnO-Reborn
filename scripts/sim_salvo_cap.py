"""Before/after table for the Fire All civilian cap (flag nuke_salvo_civilian_cap).

Runs the repo's own functions (wars.nuclear.strike_damage, wars.salvo_cap, the fallout
constants) on synthetic nations. No database. Run from the repo root:

    ENVIRONMENT=DEV python scripts/sim_salvo_cap.py

Model: every warhead hits a different province (most populated first, equal here), no
Iron Dome, no earlier strikes, all of a province's buildings counted as one type (the
real strike floors per building type, so real losses are slightly LOWER than shown).
The province shapes are synthetic: they are labelled, none is a real player's nation.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", "DEV")

from wars import aftermath, nuclear as nk, salvo_cap as sc  # noqa: E402
from wars.rules import RADIATION_DAMAGE_MULTIPLIER  # noqa: E402

FALLOUT_PCT = aftermath.NUKE_FALLOUT_DEATHS * RADIATION_DAMAGE_MULTIPLIER

# (label, population, land, cities). Buildings per province = land + cities (the slot count).
SHAPES = [
    ("new province (repo defaults: starter pop, land 1, cities 1)", 1_000_000, 1, 1),
    ("hypothetical mid (pop 1M, land 100, cities 15)", 1_000_000, 100, 15),
    (
        "large (pop 29.5M, land 3870, cities 310; from a public-page note, unverified)",
        29_500_000,
        3870,
        310,
    ),
]
SIZES = [1, 5, 20, 90]


def salvo(n_provinces, shape, warheads, capped):
    _, pop, land, cities = shape
    pops = [pop] * n_provinces
    blds = [land + cities] * n_provinces
    cits = [cities] * n_provinces
    total = (sum(pops), sum(blds), sum(cits))
    cap = sc.SalvoCap(*total) if capped else None
    fired = 0
    for i in range(min(warheads, n_provinces)):
        if cap and cap.exhausted():
            continue
        dmg = nk.strike_damage(
            {"population": pops[i], "land": land, "citycount": cits[i], "happiness": 0},
            1.0,
        )
        rem = (
            cap.remaining()
            if cap
            else {"deaths": None, "buildings": None, "cities": None}
        )
        blast = sc.clamp(dmg["deaths"], rem["deaths"])
        city_loss = sc.clamp(dmg["cities_destroyed"], rem["cities"])
        bl = sc.allocate_building_losses(
            [blds[i]], dmg["infra_frac"], rem["buildings"]
        )[0]
        if cap and cap.landed and blast == 0 and city_loss == 0 and bl == 0:
            continue  # cut to nothing: stays in stock
        pops[i] -= blast
        allowed = None if rem["deaths"] is None else max(0, rem["deaths"] - blast)
        pct = sc.fallout_pct_for_allowance(pops, FALLOUT_PCT, allowed)
        fall = sc.fallout_deaths(pops, pct)
        pops = [x - sc.fallout_deaths([x], pct) for x in pops]
        blds[i] -= bl
        cits[i] -= city_loss
        if cap:
            cap.record(blast + fall, bl, city_loss)
        fired += 1
    return (
        100.0 * (total[0] - sum(pops)) / total[0],
        100.0 * (total[1] - sum(blds)) / total[1],
        fired,
    )


def main():
    print(
        f"fallout per warhead = {FALLOUT_PCT:.4%} of every province; caps "
        f"{sc.SALVO_CIVILIAN_CAP_DEATHS:.0%} people / {sc.SALVO_CIVILIAN_CAP_BUILDINGS:.0%} "
        f"buildings / {sc.SALVO_CIVILIAN_CAP_CITIES:.0%} cities"
    )
    print("\nFULL SALVO (one warhead per province)")
    print(
        f"{'shape':<75}{'prov':>5} | {'OFF died%':>9}{'OFF bld%':>9}{'fired':>6} | "
        f"{'ON died%':>9}{'ON bld%':>9}{'fired':>6}{'kept':>6}"
    )
    for shape in SHAPES:
        for n in SIZES:
            od, ob, of = salvo(n, shape, n, False)
            nd, nb, nf = salvo(n, shape, n, True)
            print(
                f"{shape[0][:74]:<75}{n:>5} | {od:>9.1f}{ob:>9.1f}{of:>6} | "
                f"{nd:>9.1f}{nb:>9.1f}{nf:>6}{n - nf:>6}"
            )
    print("\nONE WARHEAD (must be identical OFF and ON)")
    for shape in SHAPES:
        for n in SIZES:
            a, b = salvo(n, shape, 1, False), salvo(n, shape, 1, True)
            print(
                f"{shape[0][:74]:<75}{n:>5} | OFF {a[0]:.2f}% / {a[1]:.2f}%   ON {b[0]:.2f}% / {b[1]:.2f}%"
                f"   same={a == b}"
            )


if __name__ == "__main__":
    main()
