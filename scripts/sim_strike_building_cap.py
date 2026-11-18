"""Before/after table for the drone / cruise missile building cap (flag strike_building_cap).

    ENVIRONMENT=DEV python scripts/sim_strike_building_cap.py

Rules come from wars/routes.py (read): drones hit 50% to 90% of the drones that get
through (shown at 70%), 2 damage points per hit; cruise missiles 8 points each;
STRIKE_TARGET_THRESHOLDS points per building. No interception in this table. Gold figures
are variables.MILDICT activation prices and variables.PROVINCE_UNIT_PRICES building prices
(gold only; buildings also need resources).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", "DEV")

import variables  # noqa: E402
from wars import strike_building_cap as cap  # noqa: E402
from wars.routes import STRIKE_TARGET_THRESHOLDS  # noqa: E402

DRONE_PRICE = variables.MILDICT["kamikaze_drones"]["price"]
MISSILE_PRICE = variables.MILDICT["cruise_missiles"]["price"]
# (strike target key in STRIKE_TARGET_THRESHOLDS, building name)
BUILDINGS = [("farms", "farms"), ("steel_mills", "steel_mills"), ("silo", "silos")]


def price(name):
    return variables.PROVINCE_UNIT_PRICES.get(f"{name}_price")


def row(weapon, n, target, building, stock):
    if weapon == "drones":
        points = int(n * 0.7) * 2
        cost = n * DRONE_PRICE
    else:
        points = n * 8
        cost = n * MISSILE_PRICE
    wanted = points // STRIKE_TARGET_THRESHOLDS[target]
    off = cap.capped_destroyed(stock, wanted, None)
    on = cap.capped_destroyed(stock, wanted, cap.STRIKE_BUILDING_MAX_SHARE)
    rebuild_off = (price(building) or 0) * off
    rebuild_on = (price(building) or 0) * on
    print(
        f"{weapon:>8}{n:>6}{building:>13}{stock:>7} | {off:>5}{on:>5} | "
        f"{cost:>16,}{rebuild_off:>18,}{rebuild_on:>17,}"
    )


def main():
    print(
        f"share cap {cap.STRIKE_BUILDING_MAX_SHARE:.0%}, min {cap.STRIKE_BUILDING_MIN_PER_STRIKE}"
    )
    print(
        f"{'weapon':>8}{'sent':>6}{'building':>13}{'owned':>7} | {'OFF':>5}{'ON':>5} | "
        f"{'activation gold':>16}{'rebuild gold OFF':>18}{'rebuild gold ON':>17}"
    )
    for weapon, sizes in (("drones", (100, 1000, 5000)), ("cruise", (20, 100))):
        for target, building in BUILDINGS:
            for stock in (20, 200, 1000):
                for n in sizes:
                    row(weapon, n, target, building, stock)


if __name__ == "__main__":
    main()
