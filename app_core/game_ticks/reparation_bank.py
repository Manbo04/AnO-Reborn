"""Reparations on resources a war loser has parked in a coalition bank (flag: reparation_taxes_bank).

The daily reparation tax takes 20% (Raze 5%) of the loser's 15 stockpile resources. Resources the loser
deposited into a coalition bank sat outside that base, so a loser could dodge the tax by parking stock there.
With the flag on, the loser's personal bank balance (deposited minus withdrawn, per coalition and resource)
is taxed at the same rate and paid to the winner. Pooled coalition funds (what other members put in) are
never touched. Gold is not part of the reparation base, so the bank's money is not taxed either.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

FLAG_KEY = "reparation_taxes_bank"


def enabled() -> bool:
    try:
        from app_core import feature_flags

        return feature_flags.is_on(FLAG_KEY, None, False)
    except Exception:
        return False


def tax_bank_balance(db, loser: int, winner: int, rate: float, resources) -> dict:
    """Move rate x personal balance of each resource from the loser's coalition bank share to the winner.

    Returns {resource: taken}. The caller's transaction commits. Each amount is clamped to the personal
    balance and to what the bank really holds, so pooled funds of other members are never used.
    """
    from app_core.economy import ledger

    taken_total: dict = {}
    db.execute(
        "SELECT coalition_id, resource, total_deposited, COALESCE(total_withdrawn, 0) "
        "FROM col_bank_contributions WHERE user_id = %s AND resource = ANY(%s) "
        "ORDER BY coalition_id, resource FOR UPDATE",
        (loser, list(resources)),
    )
    for coalition_id, resource, deposited, withdrawn in db.fetchall():
        personal = max(0, int(deposited) - int(withdrawn))
        want = int(personal * rate)
        if want <= 0:
            continue
        # resource is checked against the fixed Economy.resources names, so the column name is safe
        if resource not in tuple(resources):
            continue
        db.execute(f"SELECT {resource} FROM colbanks WHERE colid = %s FOR UPDATE", (coalition_id,))
        held = db.fetchone()
        if held is None:
            continue
        removed = min(want, max(0, int(held[0] or 0)))
        if removed <= 0:
            continue
        db.execute(f"UPDATE colbanks SET {resource} = {resource} - %s WHERE colid = %s", (removed, coalition_id))
        db.execute(
            "UPDATE col_bank_contributions SET total_withdrawn = COALESCE(total_withdrawn, 0) + %s "
            "WHERE coalition_id = %s AND user_id = %s AND resource = %s",
            (removed, coalition_id, loser, resource),
        )
        db.execute(
            "INSERT INTO col_bank_transactions (coalition_id, user_id, actor_id, resource, amount, direction, kind) "
            "VALUES (%s, %s, %s, %s, %s, 'withdraw', 'reparation')",
            (coalition_id, loser, winner, resource, removed),
        )
        ledger.credit_resources(db, winner, {resource: removed})
        taken_total[resource] = taken_total.get(resource, 0) + removed
    return taken_total
