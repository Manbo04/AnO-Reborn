# stats to be used in all tests:
"""
- let n = number of units
- let v = very slight random advantage/disadvantage (0.5/1.5)
- let m = morale between 1 - 100 (inclusive)
- let t = tech score - between 1 - 30
- let e = effectiveness - between 0-2
"""

n1 = 50
v1 = 1
m1 = 50
t1 = 20
e1 = 1

n2 = 50
v2 = 1
m2 = 50
t2 = 20
e2 = 1.1


def x(n: int, v: float, m: float, t: float, e: float) -> float:
    """Compute a simple battle score for a group.

    Parameters are:
    - n: number of units
    - v: small advantage modifier (e.g., 0.5 - 1.5)
    - m: morale (1-100)
    - t: tech score (1-30)
    - e: effectiveness (0-2)

    Returns: numeric score (not rounded).
    """

    return (n + v) * ((t * e) / 10 + m)


if __name__ == "__main__":
    # Quick command-line demo for manual testing
    print(f"Group 1: {int(x(n1, v1, m1, t1, e1))}")
    print(f"Group 2: {int(x(n2, v2, m2, t2, e2))}")

# Note: this file contains a small reference formula used for experimenting with
# combat calculations. Consider moving the function into the attack module when
# it's promoted for production use.
