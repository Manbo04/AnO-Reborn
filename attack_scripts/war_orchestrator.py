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
from database import get_db_connection, get_request_cursor, fetchone_first
from helpers import record_war_event
from attack_scripts.combat_helpers import compute_user_army_strength
import logging

logger = logging.getLogger(__name__)


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

        db.execute(
            "SELECT unit_id FROM unit_dictionary WHERE LOWER(name)=LOWER(%s) "
            "AND is_active=TRUE",
            (unit_name,),
        )
        unit_row = db.fetchone()
        if not unit_row:
            continue
        unit_id = unit_row[0]

        db.execute(
            """
            INSERT INTO user_military (user_id, unit_id, quantity)
            VALUES (%s, %s, 0)
            ON CONFLICT (user_id, unit_id) DO NOTHING
            """,
            (user_id, unit_id),
        )
        db.execute(
            "SELECT COALESCE(quantity, 0) "
            "FROM user_military WHERE user_id=%s AND unit_id=%s",
            (user_id, unit_id),
        )
        row = db.fetchone()
        available = row[0] if row and row[0] is not None else 0
        
        # Defensive: ensure integer amounts (legacy code used floor/int)
        try:
            loss = int(amount)
        except Exception:
            loss = int(float(amount))
            
        loss = max(0, loss)
            
        if loss > available:
            loss = available

        db.execute(
            "UPDATE user_military SET quantity=%s WHERE user_id=%s AND unit_id=%s",
            (available - loss, user_id, unit_id),
        )


_NORMAL_UNIT_NAMES = {
    "soldiers",
    "tanks",
    "artillery",
    "bombers",
    "fighters",
    "apaches",
    "destroyers",
    "cruisers",
    "submarines",
}


def resolve_defender_composition(defender_id: int) -> Tuple[list, dict]:
    """Determine the 3 unit types (and quantities) an incoming attack can hit.

    Prefers the defender's saved `/defense` composition (`Military.get_defense`).
    Falls back to the top-3-owned-by-quantity auto-pick
    (`Military.get_defending_units`) when the saved composition is missing or
    invalid (not exactly 3 known unit types) — this preserves existing
    behaviour for players who never configured `/defense`.

    Returns (defenselst, defenseunits) where defenselst is the ordered list of
    3 unit type names and defenseunits maps unit type -> quantity owned.
    """
    from attack_scripts.Nations import Military

    saved = Military.get_defense(defender_id)
    if len(saved) == 3 and all(u in _NORMAL_UNIT_NAMES for u in saved):
        defender_military = Military.get_military(defender_id)
        defenseunits = {u: defender_military.get(u, 0) for u in saved}
        return saved, defenseunits

    defenseunits = Military.get_defending_units(defender_id)
    return list(defenseunits.keys()), defenseunits


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
    # Use an INDEPENDENT connection so casualties + morale drop persist even if
    # a later step in the request (loot transfer, infra damage, discord notify,
    # warResult render) raises and the request-scoped transaction rolls back.
    # Previously this used get_request_cursor() and downstream failures wiped
    # every fight's outcome — see 2026-07-03 Terra Homeworld report.
    with get_db_connection() as conn:
        db = conn.cursor()

        winner_strength_before = compute_user_army_strength(winner.user_id)
        loser_strength_before = compute_user_army_strength(loser.user_id)

        # Persist casualties for both sides in one transaction
        _apply_casualties(db, winner.user_id, winner_pairs)
        _apply_casualties(db, loser.user_id, loser_pairs)

        winner_strength_after = compute_user_army_strength(winner.user_id)
        loser_strength_after = compute_user_army_strength(loser.user_id)

        # Locate the active war row (preserve legacy behaviour of using the
        # most-recent matching row). Use the same selection filter as the
        # legacy `morale_change` implementation.
        db.execute(
            "SELECT id FROM wars WHERE "
            "((attacker=%s AND defender=%s) OR (attacker=%s AND defender=%s)) "
            " AND peace_date IS NULL",
            (
                winner.user_id,
                loser.user_id,
                loser.user_id,
                winner.user_id,
            ),
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

            # (Legacy compatibility) The old code checked if `win_type >= 4`
            # and applied fixed morale drops instead of `computed_morale_delta`.
            if win_type is not None:
                if win_type >= 4:
                    morale_delta = 20
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

                if win_type != "Sustained" and war_id is not None:
                    Nation.set_peace(db, db.connection, war_id)
                # Check for Looting Teams upgrade
                from app_core.upgrades.services import get_upgrades
                winner_upgrades = get_upgrades(winner.user_id, db=db)
                loot_multiplier = 0.3 if winner_upgrades.get("lootingteams") else 0.2

                # Transfer resources from loser to winner
                for resource in Economy.resources:
                    db.execute(
                        """
                        SELECT COALESCE(ue.quantity, 0)
                        FROM resource_dictionary rd
                        LEFT JOIN user_economy ue
                            ON ue.resource_id = rd.resource_id AND ue.user_id=%s
                        WHERE rd.name=%s AND rd.is_active=TRUE
                        """,
                        (loser.user_id, resource),
                    )
                    resource_amount = fetchone_first(db, 0) or 0
                    transfer_amount = int(float(resource_amount) * loot_multiplier)

                    db.execute(
                        """
                        INSERT INTO user_economy (user_id, resource_id, quantity)
                        SELECT %s, rd.resource_id, 0
                        FROM resource_dictionary rd
                        WHERE rd.name=%s AND rd.is_active=TRUE
                        ON CONFLICT (user_id, resource_id) DO NOTHING
                        """,
                        (loser.user_id, resource),
                    )
                    db.execute(
                        """
                        INSERT INTO user_economy (user_id, resource_id, quantity)
                        SELECT %s, rd.resource_id, 0
                        FROM resource_dictionary rd
                        WHERE rd.name=%s AND rd.is_active=TRUE
                        ON CONFLICT (user_id, resource_id) DO NOTHING
                        """,
                        (winner.user_id, resource),
                    )

                    db.execute(
                        """
                        UPDATE user_economy ue
                        SET quantity = %s
                        FROM resource_dictionary rd
                        WHERE ue.user_id=%s
                          AND ue.resource_id = rd.resource_id
                          AND rd.name=%s
                          AND rd.is_active=TRUE
                        """,
                        (resource_amount - transfer_amount, loser.user_id, resource),
                    )
                    db.execute(
                        """
                        SELECT COALESCE(ue.quantity, 0)
                        FROM resource_dictionary rd
                        LEFT JOIN user_economy ue
                            ON ue.resource_id = rd.resource_id AND ue.user_id=%s
                        WHERE rd.name=%s AND rd.is_active=TRUE
                        """,
                        (winner.user_id, resource),
                    )
                    winner_amount = fetchone_first(db, 0) or 0
                    db.execute(
                        """
                        UPDATE user_economy ue
                        SET quantity = %s
                        FROM resource_dictionary rd
                        WHERE ue.user_id=%s
                          AND ue.resource_id = rd.resource_id
                          AND rd.name=%s
                          AND rd.is_active=TRUE
                        """,
                        (winner_amount + transfer_amount, winner.user_id, resource),
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

            try:
                logger.info(
                    "war_strength_snapshot",
                    extra={
                        "war_id": war_id,
                        "winner": winner.user_id,
                        "loser": loser.user_id,
                        "winner_strength_before": winner_strength_before,
                        "winner_strength_after": winner_strength_after,
                        "loser_strength_before": loser_strength_before,
                        "loser_strength_after": loser_strength_after,
                    },
                )
            except Exception:
                pass
        # End of get_db_connection context block — commits automatically on exit

    return _determine_win_label(win_type)


# Backwards-compatible alias used by existing callers in the codebase
def morale_change(column, win_type, winner, loser):
    # Preserve signature/behavior by delegating to persist_fight_results.
    # (the `computed_morale_delta` is expected to be attached to `loser` by callers)
    computed = getattr(loser, "_computed_morale_delta", None)
    return persist_fight_results(
        winner, loser, [], [], column, computed_morale_delta=computed, win_type=win_type
    )
