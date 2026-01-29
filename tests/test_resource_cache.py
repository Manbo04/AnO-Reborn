import time

from database import query_cache, invalidate_user_cache


def test_invalidate_user_cache():
    user_id = 123456

    # Seed cache entries
    query_cache.set(f"resources_{user_id}", {"rations": 500, "lumber": 200})
    query_cache.set(f"influence_{user_id}", 9999)

    assert query_cache.get(f"resources_{user_id}") is not None
    assert query_cache.get(f"influence_{user_id}") is not None

    # Invalidate and verify removal
    invalidate_user_cache(user_id)

    assert query_cache.get(f"resources_{user_id}") is None
    assert query_cache.get(f"influence_{user_id}") is None


def test_per_key_ttl_expiry():
    key = "foo_ttl_test"

    # Cache with very short TTL
    query_cache.set(key, "value", ttl_seconds=1)

    assert query_cache.get(key) == "value"

    # Wait for it to expire
    time.sleep(1.5)

    assert query_cache.get(key) is None

    # Cache with no expiry (ttl_seconds=0)
    query_cache.set(key, "permanent", ttl_seconds=0)
    assert query_cache.get(key) == "permanent"
