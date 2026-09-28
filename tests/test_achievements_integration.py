"""
tests/test_achievements_integration.py

Integration test for check_achievements().

Setup:
  Creates a fresh `ach_t` DB using scratchpad/mkdb.sh bootstrap:
    - psql -h localhost -p 55450 -U postgres -qc "DROP DATABASE IF EXISTS ach_t" -c "CREATE DATABASE ach_t"
    - init_db_railway.py
    - scripts/apply_schema_compat.py
    - migrations/000*.sql, migrations/0010*.sql, migrations/01*.py, migrations/016*.sql
    - scripts/apply_all_pending_migrations.py
  Seeds test users (neither is id=1):
    - First run: inserts unlocked achievements, writes ZERO news rows (silent backfill).
    - Second run after a new qualifying event: writes EXACTLY ONE news row.

Run directly:
    python3 tests/test_achievements_integration.py

Or via pytest:
    pytest tests/test_achievements_integration.py -v
"""

import glob
import os
import subprocess
import sys
from pathlib import Path

# ── point the app at our test DB before any app imports ──────────────────────
TEST_DB_URL = "postgresql://postgres@localhost:55450/ach_t"
os.environ["DATABASE_PUBLIC_URL"] = TEST_DB_URL
os.environ["DATABASE_URL"] = TEST_DB_URL

# Add project root to path so imports resolve correctly.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import psycopg2


def _connect(db: str = "ach_t") -> psycopg2.extensions.connection:
    conn = psycopg2.connect(f"postgresql://postgres@localhost:55450/{db}")
    conn.autocommit = True
    return conn


def bootstrap_test_db() -> None:
    """Drop and recreate ach_t using mkdb.sh-style bootstrap."""
    db_name = "ach_t"
    db_url = f"postgresql://postgres@localhost:55450/{db_name}"
    env = os.environ.copy()
    env["DATABASE_URL"] = db_url
    env.pop("DATABASE_PUBLIC_URL", None)

    # 1. Create fresh database ach_t
    subprocess.run(
        [
            "psql",
            "-h",
            "localhost",
            "-p",
            "55450",
            "-U",
            "postgres",
            "-qc",
            f"DROP DATABASE IF EXISTS {db_name}",
            "-c",
            f"CREATE DATABASE {db_name}",
        ],
        check=True,
        capture_output=True,
    )

    py = sys.executable
    # 2. init_db_railway.py
    subprocess.run([py, "init_db_railway.py"], cwd=str(ROOT), env=env, check=True, capture_output=True)
    # 3. scripts/apply_schema_compat.py
    subprocess.run([py, "scripts/apply_schema_compat.py"], cwd=str(ROOT), env=env, check=True, capture_output=True)
    # 4. baseline migrations
    for pattern in ["migrations/000*.sql", "migrations/0010*.sql", "migrations/01*.py", "migrations/016*.sql"]:
        for f in sorted(glob.glob(str(ROOT / pattern))):
            if f.endswith(".sql"):
                subprocess.run(["psql", "-q", db_url, "-f", f], check=True, capture_output=True)
            else:
                subprocess.run([py, f], env=env, check=True, capture_output=True)
    # 5. scripts/apply_all_pending_migrations.py (includes 0095_achievements.sql)
    subprocess.run([py, "scripts/apply_all_pending_migrations.py"], cwd=str(ROOT), env=env, check=True, capture_output=True)


def test_achievements_two_runs() -> None:
    """
    1. Seed test users (not id=1):
       - User 16 qualifies for eco_treasury_1b (gold >= 1B).
       - User 17 does not qualify yet (gold = 500M).
    2. First check_achievements() call:
       - eco_treasury_1b had zero rows before this run.
       - Backfills User 16 silently, writes ZERO news rows.
    3. Trigger a qualifying event:
       - User 17 gold increases to 1B (qualifying for eco_treasury_1b).
    4. Second check_achievements() call:
       - eco_treasury_1b already has rows from run 1.
       - Unlocks for User 17, writes EXACTLY ONE news row.
    """
    # ── rebuild DB from scratch ───────────────────────────────────────────────
    bootstrap_test_db()

    # ── psycopg2 connection pool caches the old DB ref; reset it ─────────────
    import database

    try:
        database.db_pool._pool.closeall()
    except Exception:
        pass
    database.db_pool._pool = None
    database.db_pool._available = None
    database.db_pool._pid = None

    # ── seed test users (neither is id 1) ────────────────────────────────────
    user1_id = 16
    user2_id = 17
    assert user1_id != 1, "test user must not be id=1"
    assert user2_id != 1, "test user must not be id=1"

    conn = _connect()
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO users (id, username, email, date, hash) "
        "VALUES (%s, 'Tester of the Game', 'tester@example.com', '2026-01-01', 'x')",
        (user1_id,),
    )
    cur.execute(
        "INSERT INTO users (id, username, email, date, hash) "
        "VALUES (%s, 'Player Two', 'player2@example.com', '2026-01-01', 'x')",
        (user2_id,),
    )

    # User 16 qualifies for eco_treasury_1b (1B gold)
    cur.execute(
        "INSERT INTO stats (id, location, gold) VALUES (%s, 'Capital16', 1000000000)",
        (user1_id,),
    )
    # Explicitly set population below 1M so pop_1m does not interfere
    cur.execute(
        "INSERT INTO provinces (userid, provincename, citycount, land, population) "
        "VALUES (%s, 'Prov16', 1, 1, 500000)",
        (user1_id,),
    )

    # User 17 has 500M gold (does not qualify yet)
    cur.execute(
        "INSERT INTO stats (id, location, gold) VALUES (%s, 'Capital17', 500000000)",
        (user2_id,),
    )
    cur.execute(
        "INSERT INTO provinces (userid, provincename, citycount, land, population) "
        "VALUES (%s, 'Prov17', 1, 1, 500000)",
        (user2_id,),
    )
    conn.close()

    # ── import check_achievements after DB env is set ─────────────────────────
    from app_core.game_ticks.achievements import check_achievements

    # ── FIRST RUN (silent backfill) ───────────────────────────────────────────
    check_achievements()

    conn = _connect()
    cur = conn.cursor()

    cur.execute(
        "SELECT key FROM user_achievements WHERE user_id = %s ORDER BY key",
        (user1_id,),
    )
    first_unlocks = [r[0] for r in cur.fetchall()]
    print(f"[test] First run unlocks for user {user1_id}: {first_unlocks}")
    assert "eco_treasury_1b" in first_unlocks, (
        f"Expected eco_treasury_1b to be unlocked; got {first_unlocks}"
    )

    # Verify user_achievements has rows inserted
    cur.execute("SELECT COUNT(*) FROM user_achievements")
    total_unlocked_run1 = cur.fetchone()[0]
    assert total_unlocked_run1 >= 1, "First run must insert unlocked achievements"

    # Assert first run writes ZERO news rows across the entire DB
    cur.execute("SELECT COUNT(*) FROM news")
    news_count_after_first = cur.fetchone()[0]
    print(f"[test] News rows after first run: {news_count_after_first}")
    assert news_count_after_first == 0, (
        f"First run must write ZERO news rows (silent backfill); "
        f"got {news_count_after_first}"
    )

    # ── Trigger a new qualifying event (User 17 reaches 1B gold) ──────────────
    cur.execute(
        "UPDATE stats SET gold = 1000000000 WHERE id = %s",
        (user2_id,),
    )
    conn.close()

    # ── SECOND RUN ────────────────────────────────────────────────────────────
    check_achievements()

    conn = _connect()
    cur = conn.cursor()

    cur.execute(
        "SELECT key FROM user_achievements WHERE user_id = %s ORDER BY key",
        (user2_id,),
    )
    second_unlocks_user2 = [r[0] for r in cur.fetchall()]
    print(f"[test] Second run unlocks for user {user2_id}: {second_unlocks_user2}")
    assert "eco_treasury_1b" in second_unlocks_user2, (
        f"Expected eco_treasury_1b for user {user2_id}; got {second_unlocks_user2}"
    )

    cur.execute("SELECT destination_id, message FROM news")
    news_rows = cur.fetchall()
    print(f"[test] News rows after second run: {news_rows}")
    assert len(news_rows) == 1, (
        f"Second run must write EXACTLY ONE news row; got {len(news_rows)}: {news_rows}"
    )
    dest_id, msg = news_rows[0]
    assert dest_id == user2_id, f"News destination must be user {user2_id}; got {dest_id}"
    assert "Billionaire Club" in msg or "eco_treasury_1b" in msg, (
        f"News message must mention the achievement; got: {msg}"
    )

    conn.close()
    print("[test] PASSED: test_achievements_two_runs")


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_achievements_two_runs()
    print("All tests passed.")
