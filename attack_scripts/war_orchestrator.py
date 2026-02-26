"""
Orchestration / persistence helpers for fight outcomes.

This module centralises the DB-side effects that previously lived inside
`attack_scripts/Nations.py` (morale updates, casualty writes, war termination
and resource transfers). Keeping these in one place makes `fight` easier to
unit-test and prepares the codebase for a future split between pure combat
calculation and side-effectful persistence.

Public API:
- persist_fight_results(winner, loser, winner_pairs, loser_pairs, morale_column,
  computed_morale_delta=None, win_type=None) -> str
    Apply casualties and persist morale changes in a single DB transaction.

Implementation notes:
- Behaviour is kept identical to the legacy implementation (same DB tables
  updated, same win_type -> win_condition mapping, same resource transfer on
  war end).
- Uses `get_db_connection()` and `fetchone_first` from `database` for parity.
"""
from typing import Iterable, Tuple, Optional
import time
from database import get_db_connection, fetchone_first
from helpers import record_war_event


def _apply_casualties(db, user_id: int, pairs: Iterable[Tuple[str, float]]) -> None:
    """Update `military` rows for the given (unit_name, amount) pairs.

    `pairs` contains tuples of (unit_column_name, amount_to_remove). The
    function clamps against available values to avoid negative quantities and
    performs SQL updates within the caller's transaction.
    """
    for unit_name, amount in pairs:
        # Defensive: ensure integer amounts (legacy code used floor/int)
        try:
            loss = int(amount)
        except Exception:
            loss = int(float(amount))

        sel = f"SELECT {unit_name} FROM military WHERE id=(%s)"
        db.execute(sel, (user_id,))
        row = db.fetchone()
        available = row[0] if row and row[0] is not None else 0
        if loss > available:
            loss = available
        upd = f"UPDATE military SET {unit_name}=(%s) WHERE id=(%s)"
        db.execute(upd, (available - loss, user_id))


def _determine_win_label(win_type: Optional[int]) -> str:
    if win_type is None:
        return "close victory"
    if win_type >= 3:
        return "annihilation"
    if win_type >= 2:
        return "definite victory"
    return "close victory"


def persist_fight_results(
    winner,
    loser,
    winner_pairs,
    loser_pairs,
    morale_column: str,
    computed_morale_delta: Optional[float] = None,
    win_type: Optional[int] = None,
) -> str:
    """Persist casualties and morale change for a single fight.

    Parameters:
    - winner / loser: Units (or objects exposing user_id)
    - winner_pairs / loser_pairs: Iterable[(unit_name, amount)] for DB updates
    - morale_column: column name in `wars` to decrement on the loser side
    - computed_morale_delta: optional precomputed morale delta (preferred)
    - win_type: numeric win severity (used as fallback if delta not provided)

    Returns the human-readable win condition string ("annihilation", etc.).
    """
    with get_db_connection() as connection:
        db = connection.cursor()

        # Persist casualties for both sides in one transaction
        _apply_casualties(db, winner.user_id, winner_pairs)
        _apply_casualties(db, loser.user_id, loser_pairs)

        # Locate the active war row (preserve legacy behaviour of using the
        # most-recent matching row). Use the same selection filter as the
        # legacy `morale_change` implementation.
        db.execute(
            "SELECT id FROM wars WHERE (attacker=(%s) OR attacker=(%s)) AND (defender=(%s) OR defender=(%s))",
            (winner.user_id, winner.user_id, loser.user_id, loser.user_id),
        )
        try:
            war_id = db.fetchall()[-1][0]
        except Exception:
            war_id = None

        # Read current morale value and apply delta
        if war_id is not None:
            sel = f"SELECT {morale_column} FROM wars WHERE id=(%s)"
            db.execute(sel, (war_id,))
            current = fetchone_first(db, 0) or 0

            # Determine morale delta (prefer computed delta)
            if computed_morale_delta is None:
                if win_type is None:
                    morale_delta = 5
                elif win_type >= 3:
                    morale_delta = 15
                elif win_type >= 2:
                    morale_delta = 10
                else:
                    morale_delta = 5
            else:
                morale_delta = int(computed_morale_delta)

            new_morale = current - int(morale_delta)

            # If morale drops to zero or below, conclude the war and transfer resources
            win_label = _determine_win_label(win_type)
            if new_morale <= 0 and war_id is not None:
                # Mark peace
                from attack_scripts.Nations import Nation, Economy

                Nation.set_peace(db, connection, war_id)

                # Transfer 20% of every resource from loser to winner (perform updates directly
                # to avoid depending on other higher-level helpers).
                for resource in Economy.resources:
                    db.execute(
                        f"SELECT {resource} FROM resources WHERE id=%s",
                        (loser.user_id,),
                    )
                    resource_amount = fetchone_first(db, 0) or 0
                    transfer_amount = int(resource_amount * 0.2)

                    # Subtract from loser
                    db.execute(
                        f"UPDATE resources SET {resource}=(%s) WHERE id=%s",
                        (resource_amount - transfer_amount, loser.user_id),
                    )

                    # Add to winner
                    db.execute(
                        f"SELECT {resource} FROM resources WHERE id=%s",
                        (winner.user_id,),
                    )
                    winner_amount = fetchone_first(db, 0) or 0
                    db.execute(
                        f"UPDATE resources SET {resource}=(%s) WHERE id=%s",
                        (winner_amount + transfer_amount, winner.user_id),
                    )

            # Persist the new morale value
            db.execute(
                f"UPDATE wars SET {morale_column}=(%s) WHERE id=(%s)",
                (new_morale, war_id),
            )

            # Audit log for troubleshooting; store details of this fight so
            # ops can inspect later.  We call the helper inside the same
            # transaction so that transient failures won’t disrupt the flow.
            try:
                # `concluded` means the war was resolved in this fight
                concluded = new_morale <= 0
                record_war_event(
                    war_id,
                    winner.user_id,
                    loser.user_id,
                    winner_pairs,
                    loser_pairs,
                    morale_column,
                    morale_delta,
                    new_morale,
                    win_label,
                    concluded,
                )
            except Exception:
                pass

        connection.commit()

    return _determine_win_label(win_type)


# Backwards-compatible alias used by existing callers in the codebase
def morale_change(column, win_type, winner, loser):
    # Preserve the original signature and behavior by delegating to persist_fight_results
    # (the `computed_morale_delta` is expected to be attached to `loser` by callers)
    computed = getattr(loser, "_computed_morale_delta", None)
    return persist_fight_results(
        winner, loser, [], [], column, computed_morale_delta=computed, win_type=win_type
    )
