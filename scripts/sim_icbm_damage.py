"""Before/after table for the ICBM limits (flag icbm_damage_limits). No database.

    ENVIRONMENT=DEV python scripts/sim_icbm_damage.py

Uses units.IcbmUnit.attack for the real damage/bonus and the two functions in
app_core/military/icbm_damage.py. Units destroyed = what the formula gives (floored, as
Units.casualties does), never more than the target owns. Range is the strike's random
destruction rate, 0.3 to 0.5 (attack_scripts/Nations.py special_fight). No Iron Dome.
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", "DEV")

import units  # noqa: E402
from app_core.military import icbm_damage as ic  # noqa: E402

OWNED = [50, 500, 5000]
FIRED = [1, 2, 5, 10]


def destroyed(on, fired, owned, rate, target="destroyers"):
    eff = units.IcbmUnit(fired).attack(target)
    if on:
        raw = ic.limited_destruction(eff[0], eff[1], fired, rate, owned)
    else:
        raw = ic.legacy_destruction(eff[0], eff[1], fired, rate)
    return min(owned, int(math.floor(raw)))


def main():
    print(f"share cap {ic.ICBM_MAX_UNIT_SHARE:.0%}; units destroyed, rate 0.3 to 0.5")
    print(f"{'target stack':>12}{'ICBMs':>7} | {'OFF (today)':>16} | {'ON':>16}")
    for owned in OWNED:
        for fired in FIRED:
            off = [destroyed(False, fired, owned, r) for r in (0.3, 0.5)]
            on = [destroyed(True, fired, owned, r) for r in (0.3, 0.5)]
            print(
                f"{owned:>12}{fired:>7} | {off[0]:>7} to {off[1]:<6} | {on[0]:>7} to {on[1]:<6}"
            )
    print("\nICBMs at submarines (stack 500), rate 0.4:")
    for fired in (1, 2, 5):
        off = destroyed(False, fired, 500, 0.4, "submarines")
        on = destroyed(True, fired, 500, 0.4, "submarines")
        print(f"  {fired} ICBM(s): OFF {off} (negative = submarines ADDED), ON {on}")


if __name__ == "__main__":
    main()
