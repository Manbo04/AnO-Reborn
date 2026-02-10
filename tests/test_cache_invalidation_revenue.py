import time
from database import get_db_connection, query_cache
import tasks
import countries


def create_test_user_with_mall():
    username = f"cgtest_{int(time.time())}"
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            (
                "INSERT INTO users (username, email, hash, date, auth_type) "
                "VALUES (%s,%s,%s,%s,%s) RETURNING id"
            ),
            (username, f"{username}@example.com", "x", "2020-01-01", "normal"),
        )
        uid = db.fetchone()[0]
        db.execute(
            "INSERT INTO stats (id, gold, location) VALUES (%s,%s,%s) "
            "ON CONFLICT (id) DO NOTHING",
            (uid, 1000000, ""),
        )
        db.execute(
            "INSERT INTO resources (id, lumber, coal, rations, consumer_goods) "
            "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING",
            (uid, 0, 0, 0, 0),
        )
        # give a mall so we produce consumer_goods
        db.execute(
            "INSERT INTO proInfra (id, malls) VALUES (%s,%s) "
            "ON CONFLICT (id) DO NOTHING",
            (uid, 1),
        )
        db.execute(
            "INSERT INTO provinces (id, userId, land, cityCount, productivity) "
            "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING",
            (uid, uid, 0, 1, 50),
        )
        conn.commit()
    return uid


def cleanup_user(uid):
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("DELETE FROM provinces WHERE id=%s", (uid,))
        db.execute("DELETE FROM proInfra WHERE id=%s", (uid,))
        db.execute("DELETE FROM resources WHERE id=%s", (uid,))
        db.execute("DELETE FROM stats WHERE id=%s", (uid,))
        db.execute("DELETE FROM users WHERE id=%s", (uid,))
        conn.commit()
    try:
        from database import invalidate_user_cache

        invalidate_user_cache(uid)
    except Exception:
        pass


def test_revenue_invalidates_resources_cache(monkeypatch):
    uid = create_test_user_with_mall()
    try:
        cache_key = f"resources_{uid}"
        # prime cache with stale value
        query_cache.set(cache_key, {"consumer_goods": 0}, ttl_seconds=60)
        assert query_cache.get(cache_key) is not None

        # ensure task will run from start
        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute(
                "INSERT INTO task_cursors (task_name, last_id) "
                "VALUES (%s, %s) ON CONFLICT (task_name) DO UPDATE SET last_id=0",
                ("generate_province_revenue", 0),
            )
            db.execute(
                "UPDATE task_cursors SET last_id=0 WHERE task_name=%s",
                ("generate_province_revenue",),
            )
            conn.commit()

        # run revenue
        tasks.generate_province_revenue()

        # cache should be invalidated by task
        assert query_cache.get(cache_key) is None

        # confirm DB did increase consumer_goods
        rev = countries.get_revenue(uid)
        expected_gross = rev.get("gross", {}).get("consumer_goods", 0)
        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute("SELECT consumer_goods FROM resources WHERE id=%s", (uid,))
            row = db.fetchone()
            cg = row[0] if row and row[0] is not None else 0
        assert cg >= expected_gross

    finally:
        cleanup_user(uid)
