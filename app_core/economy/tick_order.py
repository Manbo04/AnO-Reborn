"""Where the hourly tax payout sits relative to the hourly building upkeep.

Taxes are paid by ``tax_income`` (default minute :00) and building upkeep is
charged by ``generate_province_revenue`` (default minute :25). The revenue and
province projections decide which buildings "will operate" by checking the
player's treasury against upkeep. Between the upkeep tick and the next tax
payout the treasury is at its lowest point of the hour, but the next upkeep
bill is not due until *after* taxes land. Using the bare treasury then made a
nation that had just spent its gold look like every building would idle: all
nets 0, provinces unpowered, "fixing itself" at the next tax payout (ieb /
Pharloom, 2026-09-22). This helper tells the projections when the next tax
payout is still due before the next upkeep charge, so they can count it.
"""

from __future__ import annotations

import datetime as _dt
from typing import Optional

DEFAULT_TAX_MINUTE = 0
DEFAULT_UPKEEP_MINUTE = 25


def _schedule_minute(entry_name: str, default: int) -> int:
    """First minute of an hourly celery beat entry, or ``default``."""
    try:
        from app_core.celery_schedule import CELERY_BEAT_SCHEDULE

        minutes = CELERY_BEAT_SCHEDULE[entry_name]["schedule"].minute
        return min(int(m) for m in minutes)
    except Exception:
        return default


def tax_due_before_next_upkeep(
    now: Optional[_dt.datetime] = None,
    tax_minute: Optional[int] = None,
    upkeep_minute: Optional[int] = None,
) -> bool:
    """True if the next tax payout lands before the next building upkeep."""
    if now is None:
        now = _dt.datetime.now(_dt.timezone.utc)
    if tax_minute is None:
        tax_minute = _schedule_minute("tax_income", DEFAULT_TAX_MINUTE)
    if upkeep_minute is None:
        upkeep_minute = _schedule_minute(
            "generate_province_revenue", DEFAULT_UPKEEP_MINUTE
        )
    minute = now.minute
    # Minutes until each event. 0 (the event's own minute) counts as a full
    # hour away, since that tick may already have run -- conservative.
    until_tax = (tax_minute - minute) % 60 or 60
    until_upkeep = (upkeep_minute - minute) % 60 or 60
    return until_tax < until_upkeep


def upkeep_budget(treasury: int, next_tax_income: int, now=None) -> int:
    """Gold available when the next building upkeep is charged."""
    treasury = int(treasury or 0)
    if next_tax_income and next_tax_income > 0 and tax_due_before_next_upkeep(now):
        return treasury + int(next_tax_income)
    return treasury
