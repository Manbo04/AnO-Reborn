"""Nuke rework phase 2 (flag ``nuke_rework``): Fire All salvo + auto-retaliation.

Design: docs/design/NUKE_REWORK.md. One salvo per war per side (the existing
volley gate). Warheads are spread one per enemy province, most populated first;
Iron Dome rolls per warhead, damage per province reuses wars.nuclear.execute_strike.
The influence penalty is ONE flat charge for the whole salvo (not compounding per
warhead): 75% of influence, 40% when answering a nuke. It is stored on the first
warhead that gets through and decays over 7 days like any strike.
Deferred to a later PR: per-salvo destruction caps on silos/harbours/aerodomes.
"""
from __future__ import annotations

import logging
import random

from app_core import nuke_rework
from wars.nuclear import StrikeError, execute_strike, plan_strike

logger = logging.getLogger(__name__)

SALVO_FIRST_COST = 0.75
SALVO_RETALIATION_COST = 0.40
DETECTION_BASE = 0.25
DETECTION_STAR_WARS_BONUS = 0.25


def salvo_cost(influence, is_retaliation) -> int:
    rate = SALVO_RETALIATION_COST if is_retaliation else SALVO_FIRST_COST
    return int(max(0, int(influence or 0)) * rate)


def detection_chance(has_star_wars: bool) -> float:
    return DETECTION_BASE + (DETECTION_STAR_WARS_BONUS if has_star_wars else 0.0)


def pick_targets(provinces, nukes):
    """One warhead per province, most populated first, never more than nukes."""
    ordered = sorted(provinces, key=lambda p: (-int(p.get("population") or 0), p["id"]))
    return ordered[: max(0, min(int(nukes), len(ordered)))]


def execute_salvo(db, attacker_id, war_id, auto=False) -> dict:
    """Fire every nuke you can at distinct enemy provinces. Atomic in the caller's transaction."""
    if not nuke_rework.enabled(attacker_id):
        raise StrikeError("Not available.", 404)
    db.execute("SELECT pg_advisory_xact_lock(%s)", (attacker_id,))
    plan = plan_strike(db, attacker_id, war_id)  # volley + influence gates, once
    if plan["blocked"]:
        raise StrikeError(plan["blocked"])
    targets = pick_targets(plan["provinces"], plan["nukes"])
    if not targets:
        raise StrikeError("There is nothing to target.")
    cost = salvo_cost(plan["influence"], plan["is_retaliation"])
    carried = False
    results = []
    for prov in targets:
        r = execute_strike(
            db, attacker_id, war_id, prov["id"], salvo=True,
            cost_override=0 if carried else cost,
        )
        if not r.get("intercepted"):
            carried = True
        results.append(r)
    summary = {
        "salvo": True,
        "auto": auto,
        "war_id": war_id,
        "enemy_id": plan["enemy_id"],
        "enemy_name": plan["enemy_name"],
        "attacker_name": plan["attacker_name"],
        "fired": len(results),
        "intercepted": sum(1 for r in results if r.get("intercepted")),
        "deaths": sum(int(r.get("deaths") or 0) for r in results),
        "cities_destroyed": sum(int(r.get("cities_destroyed") or 0) for r in results),
        "buildings_destroyed": sum(int(r.get("buildings_destroyed") or 0) for r in results),
        "cost": cost if carried else 0,
        "is_retaliation": plan["is_retaliation"],
        "spared_nukes": max(0, int(plan["nukes"]) - len(results)),
        "results": results,
    }
    if not auto:
        maybe_auto_retaliate(db, plan["enemy_id"], attacker_id, war_id)
    return summary


def _has_star_wars(db, user_id) -> bool:
    db.execute(
        "SELECT 1 FROM user_tech ut JOIN tech_dictionary td ON ut.tech_id = td.tech_id "
        "WHERE ut.user_id = %s AND td.name = 'star_wars_project' AND ut.is_unlocked = TRUE",
        (user_id,),
    )
    return db.fetchone() is not None


def maybe_auto_retaliate(db, victim_id, aggressor_id, war_id, rng=random.random) -> bool:
    """The victim of a strike fires back at once when they enabled auto-retaliation,
    still hold nukes, have not used their volley, and detect the launch (25%, +25% with
    Star Wars). Never raises into the caller's transaction."""
    try:
        if not nuke_rework.enabled(victim_id):
            return False
        db.execute("SELECT auto_retaliate FROM user_nuke_settings WHERE user_id=%s", (victim_id,))
        row = db.fetchone()
        if not row or not row[0]:
            return False
        if rng() >= detection_chance(_has_star_wars(db, victim_id)):
            db.execute(
                "INSERT INTO news (destination_id, message) VALUES (%s, %s)",
                (victim_id, "Your early-warning network failed to detect the launch in time. "
                            "Automatic retaliation did not trigger."),
            )
            return False
        db.execute("SAVEPOINT nuke_auto_retaliate")
        try:
            out = execute_salvo(db, victim_id, war_id, auto=True)
        except StrikeError:
            db.execute("ROLLBACK TO SAVEPOINT nuke_auto_retaliate")
            return False
        db.execute("RELEASE SAVEPOINT nuke_auto_retaliate")
        db.execute(
            "INSERT INTO news (destination_id, message) VALUES (%s, %s), (%s, %s)",
            (victim_id, f"Automatic retaliation: your nukes launched at {out['enemy_name']} "
                        f"({out['fired']} warheads, {out['intercepted']} intercepted).",
             aggressor_id, f"{out['attacker_name']}'s automatic retaliation hit you: "
                           f"{out['fired']} warheads, {out['intercepted']} intercepted."),
        )
        return True
    except Exception:
        logger.exception("auto retaliation failed for war %s", war_id)
        return False
