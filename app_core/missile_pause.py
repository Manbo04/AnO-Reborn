"""Temporary pause on missile launches (feature flag ``pause_missile_launches``).

Nuclear strikes (single and Fire All, including auto-retaliation), ICBM strikes, cruise
missile strikes and strategic airstrikes are refused while the flag is ON. The
strategic airstrike is included because it only targets nuke infrastructure (silos and
the Nuclear Testing Facility tech): left on, it would let a nation disarm opponents who
cannot answer with missiles during the pause. The flag ships OFF
(migration 20261118_1000_pause_missile_launches_flag.sql), so nothing changes until an
admin turns it on at /admin/flags (docs/CHANGE_PIPELINE.md, gate 5: kill switch).

Only LAUNCHING is blocked. Producing, stockpiling and activating missiles, buying
Iron Domes, kamikaze drone strikes and every other kind of attack keep working, and
nothing already owned is removed or refunded. Turning the flag off restores the old
behaviour at once.

Fail safe: a flag read never raises. If the flag cannot be read the answer is
"not paused" (the old behaviour), so a database hiccup cannot freeze the game.
"""

from __future__ import annotations

from app_core.feature_flags import is_on

FLAG = "pause_missile_launches"

MESSAGE = (
    "Nuclear, ICBM, cruise missile and strategic airstrike launches are paused while "
    "their balance is being fixed. Your missiles and bombers are safe and nothing "
    "was spent. Check the community Discord for updates."
)


def paused(user_id=None) -> bool:
    """True while missile launches are paused."""
    try:
        return is_on(FLAG, user_id)
    except Exception:
        return False
