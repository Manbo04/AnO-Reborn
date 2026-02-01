import time
import pytest
from database import get_db_connection
import tasks
import countries


def task_runs_table_exists():
    """Check if task_runs table exists in the database."""
    try:
        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_name='task_runs'"
            )
            return db.fetchone() is not None
    except Exception:
        return False


def create_test_user():
    username = f"revtest_{int(time.time())}"
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
            "INSERT INTO resources (id, lumber, coal, rations) VALUES (%s,%s,%s,%s) "
            "ON CONFLICT (id) DO NOTHING",
            (uid, 0, 0, 0),
        )
        db.execute(
            "INSERT INTO proInfra (id, lumber_mills) VALUES (%s,%s) "
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

    # Ensure any in-memory caches do not keep stale entries for this test user
    try:
        from database import invalidate_user_cache

        invalidate_user_cache(uid)
    except Exception:
        # Tests should not fail due to cache invalidation problems
        pass


@pytest.mark.skipif(
    not task_runs_table_exists(), reason="task_runs table does not exist in CI database"
)
def test_revenue_end_to_end_small_run(monkeypatch):
    uid = create_test_user()
    try:
        # Compute expected gross via countries.get_revenue
        rev_before = countries.get_revenue(uid)
        expected_lumber = rev_before.get("gross", {}).get("lumber", 0)

        # Ensure task can run (reset last_run)
        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute(
                "UPDATE task_runs SET last_run = now() - interval '5 minutes' "
                "WHERE task_name=%s",
                ("generate_province_revenue",),
            )
            conn.commit()

        # Run revenue once
        tasks.generate_province_revenue()

        # Fetch resources after
        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute("SELECT lumber FROM resources WHERE id=%s", (uid,))
            row = db.fetchone()
            lumber_after = row[0] if row and row[0] is not None else 0

        # When operating costs and other constraints are satisfied (we gave gold),
        # lumber should increase by at least the computed expected gross (or equal)
        assert lumber_after >= expected_lumber

    finally:
        cleanup_user(uid)
