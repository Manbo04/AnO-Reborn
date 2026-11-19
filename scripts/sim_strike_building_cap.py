"""Before/after tables for the drone / cruise missile limits (flag strike_building_cap).

    ENVIRONMENT=DEV python scripts/sim_strike_building_cap.py

Rules come from wars/routes.py (read): drones hit 50% to 90% of the drones that get
through (shown at 70%), 2 damage points per hit; cruise missiles 8 points each;
STRIKE_TARGET_THRESHOLDS points per building. No interception in these tables.
Gold: activation = variables.MILDICT price x units sent; building = the game's rebuild
gold price (app_core/economy/building_costs.py get_build_cost, no policy discount).
"ratio" = rebuild gold of the buildings destroyed per gold of units committed.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", "DEV")

from wars import strike_building_cap as cap  # noqa: E402
from wars.routes import STRIKE_TARGET_THRESHOLDS  # noqa: E402

UNIT = {"drones": "kamikaze_drones", "cruise": "cruise_missiles"}
# (strike target key in STRIKE_TARGET_THRESHOLDS, building name)
BUILDINGS = [("farms", "farms"), ("steel_mills", "steel_mills"), ("silo", "silos")]
KS = (5, 10, 20, 50)


def wanted_for(weapon, n, target):
    points = int(n * 0.7) * 2 if weapon == "drones" else n * 8
    return points // STRIKE_TARGET_THRESHOLDS[target]


def destroyed(weapon, n, target, building, stock, k=None, recent=0):
    wanted = wanted_for(weapon, n, target)
    if k is None:
        return cap.capped_destroyed(stock, wanted, None)
    gold = cap.unit_activation_gold(UNIT[weapon], n)
    limits = cap.StrikeLimits(
        cap.share_for(building),
        recent,
        cap.max_by_value(gold, cap.building_gold(building), k),
    )
    return cap.capped_destroyed(stock, wanted, limits)


def table():
    print(
        f"share {cap.STRIKE_BUILDING_MAX_SHARE:.0%} (silos {cap.STRIKE_SILO_MAX_SHARE:.0%}),"
        f" window {cap.STRIKE_WINDOW_HOURS}h, min {cap.STRIKE_BUILDING_MIN_PER_STRIKE};"
        f" value cap K in {KS} (default {cap.STRIKE_VALUE_CAP_MULTIPLE})"
    )
    print("cell = buildings destroyed (ratio = rebuild gold / gold of units sent)")
    head = f"{'weapon':>7}{'sent':>6}{'building':>12}{'owned':>6} | {'OFF':>14}"
    for k in KS:
        head += f" | {'K=' + str(k):>14}"
    print(head)
    for weapon, sizes in (("drones", (100, 1000, 5000)), ("cruise", (20, 100))):
        for target, building in BUILDINGS:
            price = cap.building_gold(building)
            for stock in (200, 1000):
                for n in sizes:
                    gold = cap.unit_activation_gold(UNIT[weapon], n)
                    off = destroyed(weapon, n, target, building, stock)
                    line = f"{weapon:>7}{n:>6}{building:>12}{stock:>6} | "
                    line += f"{off:>5} ({off * price / gold:>6.1f}x)"
                    for k in KS:
                        on = destroyed(weapon, n, target, building, stock, k)
                        line += f" | {on:>5} ({on * price / gold:>5.1f}x)"
                    print(line)


def worst_case_ratios():
    print("\nWorst case today: rebuild gold destroyed per gold of units, by weapon and")
    print(
        "building (stock large enough that nothing runs out; same for any unit count):"
    )
    for weapon in ("drones", "cruise"):
        for target, building in BUILDINGS:
            n = 1000 if weapon == "drones" else 100
            w = wanted_for(weapon, n, target)
            gold = cap.unit_activation_gold(UNIT[weapon], n)
            ratio = w * cap.building_gold(building) / gold
            print(f"  {weapon:>7} at {building:<12} {ratio:>9.1f}x")


def burst():
    print(
        "\nThree strikes in a row (AP allows 3 in a burst), share of the stock destroyed:"
    )
    print(
        "  per-strike cap only (round 1): 1 - 0.75^3 = "
        f"{1 - 0.75 ** 3:.1%} (1000 farms: 250, 188, 141 = 579)"
    )
    for weapon, n, target, building, stock in (
        ("drones", 5000, "farms", "farms", 1000),
        ("cruise", 100, "steel_mills", "steel_mills", 1000),
        ("drones", 5000, "silo", "silos", 1000),
    ):
        owned, lost, steps = stock, 0, []
        gold = cap.unit_activation_gold(UNIT[weapon], n)
        for _ in range(3):
            limits = cap.StrikeLimits(
                cap.share_for(building),
                lost,
                cap.max_by_value(gold, cap.building_gold(building)),
            )
            got = cap.capped_destroyed(owned, wanted_for(weapon, n, target), limits)
            owned -= got
            lost += got
            steps.append(got)
        print(
            f"  with window + value cap: {weapon} x{n} at {stock} {building}:"
            f" {steps} = {lost / stock:.1%}"
        )


if __name__ == "__main__":
    table()
    worst_case_ratios()
    burst()
