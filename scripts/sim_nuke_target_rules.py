"""Who can nuke whom (flag nuke_target_rules): rule table from the repo's own functions.

    ENVIRONMENT=DEV python scripts/sim_nuke_target_rules.py

No database. Strength is population / 1000 (wars/war_range.py). Influence from population
alone is population x POPULATION_WEIGHT (influence_formula.py); real influence also counts
units, buildings and stockpiles, which this script cannot know, so the second table is a
LOWER BOUND for any target of that size.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", "DEV")

from influence_formula import POPULATION_WEIGHT  # noqa: E402
from wars import nuke_eligibility as ne  # noqa: E402
from wars.nuclear import MIN_LAUNCH_INFLUENCE  # noqa: E402
from wars.war_range import WAR_RANGE_LOW, war_strength  # noqa: E402


def main():
    atk_pop = 300_000_000
    atk = war_strength(atk_pop)
    print(
        f"Attacker population {atk_pop:,} (strength {atk:,.0f}); target old and rich."
    )
    print(f"{'target pop / attacker pop':>26} | OFF (today)  | ON")
    for ratio in (0.5, 0.74, 0.75, 1.0, 1.33, 1.34, 2.0):
        tgt = war_strength(atk_pop * ratio)
        ok, why = ne.can_nuke(atk, tgt, 5_000_000, 400.0, False)
        print(
            f"{ratio:>26} | not checked | {'allowed' if ok else 'refused: out of range'}"
        )
    print("\nProtection and retaliation (in range, flag ON):")
    cases = [
        ("influence 99,999", 99_999, 400.0, False),
        ("influence 100,000", 100_000, 400.0, False),
        ("account 13 days old", 5_000_000, 13.0, False),
        ("account 14 days old", 5_000_000, 14.0, False),
        ("brand new, no influence, RETALIATION", 0, 0.0, True),
    ]
    for label, infl, age, retal in cases:
        ok, why = ne.can_nuke(atk, atk, infl, age, retal)
        print(f"  {label:<40} -> {'allowed' if ok else 'refused'}")
    print("\nDoes the 100,000 influence bar ever bind next to the war range?")
    print(
        f"A first strike needs {MIN_LAUNCH_INFLUENCE:,} influence (wars/nuclear.py). A target in "
        f"range holds at least {WAR_RANGE_LOW:.0%} of the attacker's population, so its "
        f"population-only influence is at least {WAR_RANGE_LOW:.0%} x attacker pop x "
        f"{POPULATION_WEIGHT}."
    )
    print(
        f"{'attacker pop':>14}{'min target pop in range':>26}{'min target influence (pop only)':>34}"
    )
    for pop in (
        10_000_000,
        26_000_000,
        27_000_000,
        100_000_000,
        300_000_000,
        2_000_000_000,
    ):
        tpop = pop * WAR_RANGE_LOW
        infl = tpop * POPULATION_WEIGHT
        print(
            f"{pop:>14,}{tpop:>26,.0f}{infl:>34,.0f}{'   <- under the bar' if infl < ne.NUKE_PROTECTION_MIN_INFLUENCE else ''}"
        )
    bar_pop = ne.NUKE_PROTECTION_MIN_INFLUENCE / POPULATION_WEIGHT / WAR_RANGE_LOW
    print(
        f"The bar can only bind for an attacker below about {bar_pop:,.0f} people (one that "
        f"small reaches {MIN_LAUNCH_INFLUENCE:,} influence only through units, buildings "
        f"and stockpiles)."
    )


if __name__ == "__main__":
    main()
