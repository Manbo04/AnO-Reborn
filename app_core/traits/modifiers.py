"""Cheap trait/blessing modifier lookup for the economy ticks.

load_all(db) returns {user_id: modifiers} for the (few) nations that have an active trait or
pilgrim blessing; every other nation is simply absent, so callers use
`mods.get(user_id, NEUTRAL)` and pay nothing. Tolerant of unmigrated tables: any failure
yields {} (the game behaves as if no trait existed).
"""
import logging

from . import golden_throne, registry

logger = logging.getLogger(__name__)

NEUTRAL = {
    "happiness_pct": 0.0,
    "industry_mult": 1.0,
    "food_mult": 1.0,
    "upkeep_mult": 1.0,
    "pop_cap_mult": 1.0,
    "defense_pct": 0.0,
}


def load_all(db):
    if registry.disabled():
        return {}
    mods = {}
    try:
        db.execute("SAVEPOINT trait_mods")
        db.execute(
            "SELECT s.user_id, s.vitality, s.crisis, s.active_event, s.event_ends_at "
            "FROM throne_state s JOIN nation_traits t "
            "ON t.user_id = s.user_id AND t.trait_key = %s AND t.enabled",
            (golden_throne.TRAIT_KEY,),
        )
        for uid, vit, crisis, ev, ends in db.fetchall():
            mods[uid] = dict(NEUTRAL, **golden_throne.holder_modifiers((vit, crisis, ev, ends)))
        db.execute("SELECT user_id, pct FROM throne_blessings WHERE expires_at > NOW()")
        for uid, pct in db.fetchall():
            m = mods.setdefault(uid, dict(NEUTRAL))
            m["happiness_pct"] += float(pct)
        db.execute("RELEASE SAVEPOINT trait_mods")
    except Exception:
        logger.debug("trait modifiers unavailable", exc_info=True)
        try:
            db.execute("ROLLBACK TO SAVEPOINT trait_mods")
        except Exception:
            pass
        return {}
    return mods
