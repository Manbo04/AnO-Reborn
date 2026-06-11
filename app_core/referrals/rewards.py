"""Referral reward definitions."""
from __future__ import annotations

INVITEE_SIGNUP_BONUS: dict[str, int] = {
    "money": 5_000_000,
    "lumber": 15_000,
}

# Inviter rewards keyed by distinct active days on the referred account.
MILESTONE_REWARDS: dict[int, dict[str, int]] = {
    1: {"money": 2_000_000, "lumber": 10_000},
    3: {"money": 3_000_000, "lumber": 15_000},
    7: {"money": 5_000_000, "lumber": 25_000, "coal": 10_000},
    14: {"money": 10_000_000, "lumber": 50_000},
}

MILESTONE_DAY_THRESHOLDS: tuple[int, ...] = tuple(sorted(MILESTONE_REWARDS.keys()))


def merge_rewards(*reward_dicts: dict[str, int]) -> dict[str, int]:
    merged: dict[str, int] = {}
    for rewards in reward_dicts:
        for key, amount in rewards.items():
            merged[key] = merged.get(key, 0) + int(amount)
    return merged


def reward_summary_text(rewards: dict[str, int]) -> str:
    parts = []
    for key, amount in sorted(rewards.items()):
        label = "gold" if key == "money" else key
        parts.append(f"+{amount:,} {label}")
    return ", ".join(parts)
