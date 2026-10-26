"""Bombers are one pool of airframes per UTC hour.

Air-support sorties, air-attack sorties and bomber precision strikes in the
same hour are added together and cannot exceed the bombers owned when the
order was given. Needs migrations/20261026_1800_bomber_sorties.sql; without
the table the check is skipped and attacks behave as before.
"""

from __future__ import annotations

import time

HOUR = 3600
ROLES = ("support", "attack", "strike")


def table_exists(db) -> bool:
    db.execute("SELECT to_regclass('public.bomber_sorties')")
    row = db.fetchone()
    return bool(row and row[0])


def _hour_bucket(now: float = None) -> int:
    return int((time.time() if now is None else now) // HOUR)


def committed_this_hour(db, user_id: int, now: float = None) -> int:
    if not table_exists(db):
        return 0
    db.execute(
        """
        SELECT COALESCE(SUM(amount), 0) FROM bomber_sorties
        WHERE user_id = %s AND hour_bucket = %s
        """,
        (user_id, _hour_bucket(now)),
    )
    row = db.fetchone()
    return int(row[0] or 0) if row else 0


def bombers_free_for(db, user_id: int, role: str, amount: int, owned: int) -> tuple:
    """True if `amount` bombers can take `role` this hour.

    Every sortie already recorded this hour, whatever its role, is already
    in the air.
    """
    amount = int(amount or 0)
    if amount <= 0:
        return True, None
    if role not in ROLES or not table_exists(db):
        return True, None
    used = committed_this_hour(db, user_id)
    free = max(0, int(owned or 0) - used)
    if amount > free:
        return False, (f"Only {free} bombers are free this hour. {used} already flew.")
    return True, None


def record_sortie(db, war_id: int, user_id: int, role: str, amount: int) -> None:
    amount = int(amount or 0)
    if amount <= 0 or role not in ROLES or not table_exists(db):
        return
    db.execute(
        """
        INSERT INTO bomber_sorties (war_id, user_id, hour_bucket, role, amount)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (war_id, user_id, _hour_bucket(), role, amount),
    )
