"""Tutorial chapter and graduation reward definitions."""
from __future__ import annotations

STARTER_GOLD = 80_000_000

CHAPTER_REWARDS: dict[int, dict[str, int]] = {
    0: {"lumber": 10_000, "rations": 5_000},
    1: {"lumber": 10_000, "rations": 5_000},
    2: {"lumber": 20_000, "coal": 10_000},
    3: {"money": 2_000_000},
    4: {"money": 2_000_000},
    5: {"iron": 10_000},
    6: {"money": 3_000_000},
    7: {"components": 5_000},
    8: {"components": 5_000},
}

GRADUATION_REWARD: dict[str, int] = {
    "money": 10_000_000,
    "lumber": 50_000,
    "coal": 50_000,
    "rations": 100_000,
}


def merge_rewards(*reward_dicts: dict[str, int]) -> dict[str, int]:
    merged: dict[str, int] = {}
    for rewards in reward_dicts:
        for key, amount in rewards.items():
            merged[key] = merged.get(key, 0) + int(amount)
    return merged
