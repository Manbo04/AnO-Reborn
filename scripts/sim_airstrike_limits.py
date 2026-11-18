"""Before/after table for the strategic airstrike limits (flag strategic_airstrike_limits).

    ENVIRONMENT=DEV python scripts/sim_airstrike_limits.py

Uses wars/airstrike_limits.py and the route's own rules: bombing power = surviving bombers
x 0.7..1.3 (shown at the 1.0 midpoint), 15 damage points per silo, tech lost at 50 points
(flag off) or 150 (flag on). Defender has no fighters. Action points: wars/action_points.py
AP_START 6, AP_MAX 12, +1 per hour; a strike costs 2 air AP with the flag on, 0 today.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", "DEV")

from wars import airstrike_limits as al  # noqa: E402
from wars.action_points import AP_REGEN_PER_HOUR, AP_START  # noqa: E402


def strikes_to_clear(silos, bombers, on, ap):
    """(strikes, hours) to destroy every silo, bombers all survive."""
    strikes, hours = 0, 0
    while silos > 0 and strikes < 1000:
        if on:
            while ap < al.STRATEGIC_AIRSTRIKE_AP_COST:
                ap += AP_REGEN_PER_HOUR
                hours += 1
            ap -= al.STRATEGIC_AIRSTRIKE_AP_COST
        pts = al.silo_damage_points(silos, bombers) if on else bombers
        silos -= min(silos, int(pts // al.SILO_DAMAGE_POINTS))
        strikes += 1
    return strikes, hours


def main():
    print("one strike, no fighters: silos destroyed (OFF today / ON)")
    print(f"{'silos':>6}{'bombers':>9} | {'OFF':>5}{'ON':>5}")
    for silos in (4, 10, 40, 100):
        for bombers in (50, 150, 500):
            off = min(silos, bombers // al.SILO_DAMAGE_POINTS)
            on = min(silos, int(al.silo_damage_points(silos, bombers) // 15))
            print(f"{silos:>6}{bombers:>9} | {off:>5}{on:>5}")
    print(
        "\nstrikes and waiting hours to destroy ALL silos (start with "
        f"{AP_START} air AP)"
    )
    print(f"{'silos':>6}{'bombers':>9} | {'OFF strikes/h':>14} | {'ON strikes/h':>13}")
    for silos in (10, 40, 100):
        for bombers in (150, 500):
            o = strikes_to_clear(silos, bombers, False, AP_START)
            n = strikes_to_clear(silos, bombers, True, AP_START)
            print(f"{silos:>6}{bombers:>9} | {o[0]:>9}/{o[1]:<4} | {n[0]:>8}/{n[1]:<4}")
    print(
        f"\nNuclear Testing Facility tech: lost at {al.tech_threshold(False)} points "
        f"(about {al.tech_threshold(False)} surviving bombers) today, "
        f"{al.tech_threshold(True)} with the flag"
    )


if __name__ == "__main__":
    main()
