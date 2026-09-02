from database import reuse_or_new_cursor
from .repositories import format_policy_flags, get_user_policy_row, update_user_policies


def get_user_policies(user_id, db=None):
    """Cross-module read API - also imported directly by countries.py and
    services/country_service.py, so this name and signature (positional
    user_id, optional db) is a real public contract to preserve exactly,
    not just an internal route helper."""
    from database import query_cache

    cache_key = f"policies_{user_id}"
    cached = query_cache.get(cache_key)
    if cached is not None:
        return cached

    with reuse_or_new_cursor(db) as cur:
        temp_policies = {}
        result = get_user_policy_row(cur, user_id)
        if result:
            soldiers_raw, education_raw = result
            temp_policies["soldiers"] = soldiers_raw if soldiers_raw is not None else []
            temp_policies["education"] = (
                education_raw if education_raw is not None else []
            )
        else:
            temp_policies["soldiers"] = []
            temp_policies["education"] = []

        policies = {}
        policies.update(format_policy_flags(temp_policies, "soldiers", 7))
        policies.update(format_policy_flags(temp_policies, "education", 6))

        query_cache.set(cache_key, policies, ttl_seconds=60)
        return policies


def save_user_policies(db, cId, military, education):
    """Only the DB write. Call invalidate_policies_cache() AFTER the
    caller's cursor context manager has committed, not before - matches the
    original's exact ordering, which avoids a race where a concurrent read
    could repopulate the cache with stale pre-update data."""
    update_user_policies(db, cId, military, education)


def invalidate_policies_cache(cId):
    from database import query_cache

    query_cache.invalidate(f"policies_{cId}")
