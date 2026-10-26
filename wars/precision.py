"""Precision strikes (balance prototype, phase 4).

Cruisers (missiles, naval AP) or bombers (air AP) hit one chosen enemy unit
type in an active war. No territory, loot or morale effect. Kills a capped
share of that type, and the survivors are disrupted for the striker's next
attack on this enemy within SUPPRESS_WINDOW_HOURS. Math lives in
attack_scripts.combat_helpers.compute_precision_strike; this module is the DB
flow. Needs migration 20261026_1400_precision_strikes.sql; without the table
the action is refused and fights are unaffected.
"""
from __future__ import annotations

from typing import Optional, Tuple

from attack_scripts import combat_helpers as ch
from wars.action_points import get_combatant_role, spend_action_points


def table_exists(db) -> bool:
    db.execute("SELECT to_regclass('public.precision_strikes')")
    row = db.fetchone()
    return bool(row and row[0])


def _owned(db, user_id, names):
    db.execute(
        """
        SELECT ud.name, COALESCE(um.quantity, 0)
        FROM unit_dictionary ud
        LEFT JOIN user_military um ON um.unit_id = ud.unit_id AND um.user_id = %s
        WHERE ud.name = ANY(%s)
        """,
        (user_id, list(names)),
    )
    out = {n: 0 for n in names}
    for name, q in db.fetchall() or []:
        out[name] = int(q or 0)
    return out


def precision_strike(db, war_id: int, user_id: int, striker: str, target_unit: str,
                     rng=None) -> Tuple[bool, str, Optional[dict]]:
    if striker not in ch.PRECISION_STRIKERS:
        return False, "Choose cruisers or bombers for a precision strike.", None
    if target_unit not in ch.PRECISION_TARGETS:
        return False, "Choose a valid enemy unit type to strike.", None
    if not table_exists(db):
        return False, "Precision strikes are not available yet.", None
    role = get_combatant_role(db, war_id, user_id)
    if not role:
        return False, "You are not a participant in this war.", None
    db.execute(
        "SELECT attacker, defender FROM wars WHERE id = %s AND status = 'active' AND peace_date IS NULL",
        (war_id,),
    )
    row = db.fetchone()
    if not row:
        return False, "This war is not active.", None
    enemy_id = row[1] if role == "attacker" else row[0]

    db.execute(
        """
        SELECT target_unit FROM precision_strikes
        WHERE war_id = %s AND attacker_id = %s AND struck_at > now() - interval '24 hours'
        """,
        (war_id, user_id),
    )
    recent = [r[0] for r in (db.fetchall() or [])]
    if len(recent) >= ch.STRIKE_DAILY_LIMIT:
        return False, f"You can make at most {ch.STRIKE_DAILY_LIMIT} precision strikes per war every 24 hours.", None
    prior = sum(1 for t in recent if t == target_unit)

    branch, cover_unit = ch.PRECISION_STRIKERS[striker]
    mine = _owned(db, user_id, [striker])[striker]
    if mine < 1:
        return False, f"You need at least 1 of your {striker} for this strike.", None
    theirs = _owned(db, enemy_id, [target_unit, cover_unit])

    ok, err = spend_action_points(db, war_id, user_id, branch, ch.PRECISION_AP_COST)
    if not ok:
        return False, err or f"Not enough {branch} action points.", None

    res = ch.compute_precision_strike(
        striker, mine, target_unit, theirs[target_unit], theirs[cover_unit], prior, rng=rng
    )
    from wars.aftermath import apply_unit_losses

    if res["killed"]:
        apply_unit_losses(db, enemy_id, {target_unit: res["killed"]})
    if res["lost"]:
        apply_unit_losses(db, user_id, {striker: res["lost"]})
    db.execute(
        """
        INSERT INTO precision_strikes
            (war_id, attacker_id, target_id, striker, target_unit, killed, lost, suppress)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (war_id, user_id, enemy_id, striker, target_unit, res["killed"], res["lost"], float(res["suppress"])),
    )
    msg = (
        f"Precision strike with {mine} {striker}: destroyed {res['killed']} enemy {target_unit}"
        f" (enemy {cover_unit} cover {round(res['cover'] * 100)}%), lost {res['lost']} {striker}."
    )
    if res["suppress"] > 0:
        msg += (f" Surviving {target_unit} fight at -{round(res['suppress'] * 100)}% strength in your"
                f" next attack within {ch.SUPPRESS_WINDOW_HOURS} hours.")
    if prior:
        msg += f" Reduced effect: {prior} earlier strike(s) on {target_unit} in the last 24 hours."
    res.update(striker=striker, strikers=mine, target_unit=target_unit, enemy_id=enemy_id)
    return True, msg, res


def consume_suppression(db, war_id: int, attacker_id: int) -> dict:
    """Disruption from this attacker's unused recent strikes, marked used."""
    if not war_id or not table_exists(db):
        return {}
    db.execute(
        """
        UPDATE precision_strikes SET consumed = TRUE
        WHERE war_id = %s AND attacker_id = %s AND NOT consumed
          AND struck_at > now() - make_interval(hours => %s)
        RETURNING target_unit, suppress
        """,
        (war_id, attacker_id, ch.SUPPRESS_WINDOW_HOURS),
    )
    out: dict = {}
    for unit, sup in db.fetchall() or []:
        out[unit] = min(ch.SUPPRESS_MAX, out.get(unit, 0.0) + float(sup or 0))
    return out
