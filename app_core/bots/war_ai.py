"""Autonomous war behaviour for bot nations.

Bots never declare war. Once a human declares on one, every run (5 min):

* the bot answers a human's peace offer (white peace once it is losing or the
  war has dragged on; offers with demands are refused);
* it digs in when it has spare ground action points (entrenchment is +10%
  ground defence per level), so a campaign against it gets harder over time;
* while the human is actively fighting, it launches a counter-attack in a
  branch it has action points for, every ``ATTACK_COOLDOWN`` seconds.

Counter-attacks use exactly what a player's attack uses: branch action points
(``wars.action_points``), entrenchment/intel modifiers, ``Military.fight`` ->
``persist_fight_results`` (casualties, morale, war-end transfer). They skip
gold looting, infrastructure damage and civilian-casualty aftermath -- a bot
pressures its enemy's morale, it doesn't strip-mine the player.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)

ATTACK_COOLDOWN = 25 * 60  # seconds between a bot's counter-attacks per war
ENGAGED_WINDOW = 36 * 3600  # human fought within this long => war is "live"
OPENING_WINDOW = 2 * 3600  # a fresh declaration also counts as live
PEACE_AFTER = 12 * 3600  # accept white peace once the war is this old...
PEACE_MORALE = 50  # ...or the bot's morale falls to this
SEND_FRACTION = (0.35, 0.6)
ATTACK_CHANCE = 0.8  # per eligible run, so timing isn't clockwork
ATTACK_AP_COST = 3
DIG_IN_MIN_AP = 5  # dig in only while >= one attack's worth of AP stays spare
ENTRENCH_MAX = 3


def pick_domain(units: Dict[str, int], ap: Dict[str, int], rng=random) -> Optional[str]:
    """Weighted-random attack branch among those the bot can afford and staff."""
    from attack_scripts.Nations import Military
    from wars.war_range import UNIT_WEIGHTS

    scores = {}
    for domain, names in Military.ATTACK_UNITS.items():
        if int(ap.get(domain, 0)) < ATTACK_AP_COST:
            continue
        score = sum(UNIT_WEIGHTS.get(n, 0) * int(units.get(n, 0)) for n in names)
        if score > 0:
            scores[domain] = score
    if not scores:
        return None
    return rng.choices(list(scores), weights=list(scores.values()))[0]


def should_accept_peace(
    *, war_age: float, bot_morale: float, has_demands: bool
) -> bool:
    from wars.rules import WAR_MIN_DURATION_SECONDS

    if has_demands or war_age < WAR_MIN_DURATION_SECONDS:
        return False
    return war_age >= PEACE_AFTER or bot_morale <= PEACE_MORALE


def should_counterattack(
    *,
    now: float,
    last_attack_at: float,
    last_human_action: float,
    started: float,
    bot_morale: float,
    roll: float,
) -> bool:
    live = (now - last_human_action) <= ENGAGED_WINDOW or (
        now - started
    ) <= OPENING_WINDOW
    return (
        live
        and bot_morale > 0
        and (now - last_attack_at) >= ATTACK_COOLDOWN
        and roll <= ATTACK_CHANCE
    )


def should_dig_in(*, ground_ap: int, entrench: int) -> bool:
    return entrench < ENTRENCH_MAX and ground_ap >= DIG_IN_MIN_AP


def _news(cur, user_id: int, message: str) -> None:
    cur.execute(
        "INSERT INTO news (destination_id, message) VALUES (%s, %s)", (user_id, message)
    )


def _handle_peace(
    cur, conn, war: dict, human_id: int, bot_morale: float, now: float
) -> bool:
    """Answer a pending human peace offer. Returns True if the war ended."""
    if not war["peace_offer_id"]:
        return False
    cur.execute(
        "SELECT author, demanded_resources FROM peace WHERE id = %s",
        (war["peace_offer_id"],),
    )
    row = cur.fetchone()
    if not row or row[0] != human_id:
        return False  # not the human's offer, or already gone
    from wars.rules import war_age_ok

    if not war_age_ok(war["start_date"], now):
        return False  # too early to end the war: leave the offer pending
    accept = should_accept_peace(
        war_age=now - float(war["start_date"] or now),
        bot_morale=bot_morale,
        has_demands=bool((row[1] or "").strip()),
    )
    if accept:
        from attack_scripts.Nations import Nation

        Nation.set_peace(
            cur,
            conn,
            None,
            {"option": "peace_offer_id", "value": war["peace_offer_id"]},
        )
        _news(
            cur,
            human_id,
            "🕊️ The AI nation accepted your peace offer. The war is over.",
        )
        return True
    cur.execute("UPDATE wars SET peace_offer_id = NULL WHERE id = %s", (war["id"],))
    cur.execute("DELETE FROM peace WHERE id = %s", (war["peace_offer_id"],))
    _news(cur, human_id, "🛡️ The AI nation rejected your peace offer and fights on.")
    return False


def _counterattack(
    cur,
    conn,
    war: dict,
    bot_id: int,
    human_id: int,
    bot_name: str,
    status: dict,
    rng=random,
) -> bool:
    """Resolve one bot attack on the human. True if a battle took place."""
    from attack_scripts.Nations import Military
    from attack_scripts.war_orchestrator import resolve_defender_composition
    from units import Units
    from wars import action_points as ap_mod
    from wars import supply as war_supply

    owned = Military.get_military(bot_id)
    domain = pick_domain(
        owned,
        {
            "ground": status.get("ground_ap", 0),
            "air": status.get("air_ap", 0),
            "naval": status.get("naval_ap", 0),
        },
        rng,
    )
    if not domain:
        return False

    frac = rng.uniform(*SEND_FRACTION)
    sent = {u: int(int(owned.get(u, 0)) * frac) for u in Military.ATTACK_UNITS[domain]}
    if not sum(sent.values()):
        return False
    attacker = Units(bot_id, war_id=war["id"])
    if attacker.attach_units(sent, len(sent)) is not None:
        return False

    ok, _err = ap_mod.spend_action_points(
        cur, war["id"], bot_id, domain, ATTACK_AP_COST
    )
    if not ok:
        conn.rollback()
        return False

    # Replay/race guard shared with player attacks (migration 0081); committed
    # before the fight, which updates this same wars row on other connections.
    now = time.time()
    cur.execute(
        "UPDATE wars SET last_attack_resolved_at = %s WHERE id = %s "
        "AND (last_attack_resolved_at IS NULL OR %s - last_attack_resolved_at >= 1) RETURNING id",
        (now, war["id"], now),
    )
    if not cur.fetchone():
        conn.rollback()  # also refunds the action points
        return False
    conn.commit()

    defenselst, defenseunits = resolve_defender_composition(human_id, domain)
    defender = Units(human_id, dict(defenseunits), selected_units_list=defenselst)
    fielded = {u: max(0, int(q or 0)) for u, q in defenseunits.items()}
    defender.selected_units = fielded
    prev_defender = dict(fielded)

    citizen_pct = None
    if domain == "ground" and sum(fielded.values()) == 0:
        pop, provs = war_supply.get_population_and_provinces(cur, human_id)
        citizen_pct = war_supply.citizen_army_pct(pop, provs)

    fight_kwargs = {
        "entrenchment_level": status.get("enemy_entrench", 0),
        "attacker_intel": status.get("my_intel", 0),
        "domain": domain,
    }
    if citizen_pct is not None:
        fight_kwargs["citizen_army_pct"] = citizen_pct
    winner, win_condition, _effects = Military.fight(attacker, defender, **fight_kwargs)

    try:
        if domain == "ground":
            ap_mod.reset_entrenchment_on_ground_attack(cur, war["id"], bot_id)
        ap_mod.consume_intel_on_attack(cur, war["id"], bot_id)
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("bots: post-attack bookkeeping failed war=%s", war["id"])

    d_losses = getattr(defender, "_fight_losses", None) or {}
    a_losses = getattr(attacker, "_fight_losses", None) or {}

    def _fmt(losses, base):
        parts = [
            f"{min(base.get(u, 0), int(q))} {u.replace('_', ' ')}"
            for u, q in losses.items()
            if int(q) > 0
        ]
        return ", ".join(parts) or "none"

    outcome = (
        f"Defeat! The AI assault broke your lines ({win_condition})."
        if winner == bot_id
        else f"Victory! You repelled the AI assault ({win_condition})."
    )
    try:
        _news(
            cur,
            human_id,
            f"⚔️ BATTLE REPORT: {bot_name} launched a {domain.title()} assault on your nation! "
            f"{outcome} Your casualties: {_fmt(d_losses, prev_defender)}. "
            f"Enemy casualties: {_fmt(a_losses, sent)}.",
        )
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("bots: battle news failed war=%s", war["id"])
    return True


def run_war_ai(conn, rng=random) -> Dict[str, int]:
    """One pass over every active war involving a bot."""
    from app_core.bots import service
    from wars import action_points as ap_mod

    cur = conn.cursor()
    service.ensure_schema(cur)
    conn.commit()
    cur.execute("""
        SELECT w.id, w.attacker, w.defender, w.peace_offer_id, w.start_date,
               w.attacker_morale, w.defender_morale, w.last_attack_resolved_at,
               bn.user_id, u.username,
               COALESCE(s.last_attack_at, 0), COALESCE(s.bot_guard_ts, 0),
               COALESCE(s.human_action_ts, 0)
        FROM wars w
        JOIN bot_nations bn ON bn.user_id IN (w.attacker, w.defender)
        JOIN users u ON u.id = bn.user_id
        LEFT JOIN bot_war_state s ON s.war_id = w.id
        WHERE w.peace_date IS NULL
        """)
    now = time.time()
    stats = {"wars": 0, "attacks": 0, "peace": 0, "dig_ins": 0}
    for row in cur.fetchall():
        (
            wid,
            att,
            dfn,
            offer,
            start,
            a_mor,
            d_mor,
            last_res,
            bot_id,
            bot_name,
            last_attack,
            bot_guard_ts,
            human_ts,
        ) = row
        stats["wars"] += 1
        war = {"id": wid, "peace_offer_id": offer, "start_date": start}
        bot_is_attacker = bot_id == att
        human_id = dfn if bot_is_attacker else att
        bot_morale = (a_mor if bot_is_attacker else d_mor) or 0
        # The bot's own attacks also stamp last_attack_resolved_at (shared
        # replay guard), so a newer stamp than the bot's last one is a human attack.
        if last_res and float(last_res) > float(bot_guard_ts) + 0.001:
            human_ts = float(last_res)
        try:
            if _handle_peace(cur, conn, war, human_id, bot_morale, now):
                stats["peace"] += 1
                continue
            conn.commit()

            status = ap_mod.get_war_combat_status(cur, wid, bot_id)
            did_attack = 0
            attacked = should_counterattack(
                now=now,
                last_attack_at=float(last_attack or 0),
                last_human_action=float(human_ts or 0),
                started=float(start or 0),
                bot_morale=bot_morale,
                roll=rng.random(),
            ) and _counterattack(
                cur, conn, war, bot_id, human_id, bot_name, status, rng
            )
            if attacked:
                cur.execute(
                    "SELECT last_attack_resolved_at FROM wars WHERE id = %s", (wid,)
                )
                guard = (cur.fetchone() or [now])[0] or now
                stats["attacks"] += 1
                did_attack = 1
                last_attack, bot_guard_ts = now, float(guard)
            elif should_dig_in(
                ground_ap=int(status.get("ground_ap") or 0),
                entrench=int(status.get("my_entrench") or 0),
            ):
                ok, _msg, _lvl = ap_mod.dig_in(cur, wid, bot_id)
                if ok:
                    stats["dig_ins"] += 1
            cur.execute(
                "INSERT INTO bot_war_state (war_id, last_attack_at, attacks, bot_guard_ts, human_action_ts) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (war_id) DO UPDATE SET "
                "last_attack_at = EXCLUDED.last_attack_at, "
                "attacks = bot_war_state.attacks + %s, "
                "bot_guard_ts = EXCLUDED.bot_guard_ts, human_action_ts = EXCLUDED.human_action_ts",
                (wid, last_attack, did_attack, bot_guard_ts, human_ts, did_attack),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            logger.exception("bots: war AI failed for war %s", wid)
    return stats
