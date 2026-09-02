"""No Flask imports in this file: get_upgrades() is imported directly by
Celery-context code (attack_scripts/war_orchestrator.py, attack_scripts/Nations.py)
where a Flask app/request context isn't available. (database.py itself still
pulls in Flask transitively either way - same as it always did before this
migration - so this doesn't fully isolate callers from Flask being *importable*;
it just keeps this module from needing an active Flask app/request context,
which is what actually mattered for the original's defensive
`try: bp = Blueprint(...) except: bp = None` guard in routes.py.)
"""
from database import query_cache, reuse_or_new_cursor

from .repositories import (
    LEGACY_UPGRADE_TO_TECH,
    TECH_TO_LEGACY_UPGRADE,
    get_unlocked_tech_names,
    get_active_tech_catalog,
    get_unlocked_tech_ids,
)


def get_upgrades(cId, db=None):
    """Cross-module read API - imported directly by attack_scripts/Nations.py,
    attack_scripts/war_orchestrator.py, and app_core/military/services.py, not
    just used internally. Name and signature (positional cId, optional db)
    preserved exactly as a public contract."""
    cache_key = f"upgrades_{cId}"
    cached = query_cache.get(cache_key)
    if cached is not None:
        return cached

    with reuse_or_new_cursor(db) as cur:
        result = {key: False for key in LEGACY_UPGRADE_TO_TECH.keys()}
        for tech_name in get_unlocked_tech_names(cur, cId):
            legacy_key = TECH_TO_LEGACY_UPGRADE.get(tech_name)
            if legacy_key:
                result[legacy_key] = True

        # Cache for 5 minutes (query_cache's default TTL)
        query_cache.set(cache_key, result)
        return result


def build_upgrades_page_data(db, cId):
    """Shapes everything the /upgrades template needs: the tech catalog rows,
    which ones this player has unlocked, and per-tech cost/prerequisite
    display info. Players had no way to see a tech's prerequisite before
    attempting to research it and hitting a generic error - this surfaces it
    up front instead."""
    tech_rows = get_active_tech_catalog(db)

    tech_id_to_display_name = {row[0]: row[1] for row in tech_rows}
    tech_costs = {}
    tech_prereq_names = {}
    for row in tech_rows:
        tech_id, display_name, research_cost, prerequisite_tech_id, tech_name, description = row
        legacy_key = TECH_TO_LEGACY_UPGRADE.get(tech_name)
        if not legacy_key:
            continue
        tech_costs[legacy_key] = int(research_cost)
        if prerequisite_tech_id:
            tech_prereq_names[legacy_key] = tech_id_to_display_name.get(
                prerequisite_tech_id, "an earlier technology"
            )

    unlocked_ids = get_unlocked_tech_ids(db, cId)

    return tech_rows, unlocked_ids, tech_costs, tech_prereq_names


def invalidate_upgrade_caches(cId):
    from database import invalidate_user_cache, invalidate_view_cache

    try:
        invalidate_user_cache(cId)
        query_cache.invalidate(pattern=f"upgrades_{cId}")
        invalidate_view_cache("military", user_id=cId)
    except Exception:
        pass
