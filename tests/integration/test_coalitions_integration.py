import os
import time

import psycopg2
import pytest


def _connect_db():
    return psycopg2.connect(
        database=os.getenv("PG_DATABASE"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        host=os.getenv("PG_HOST"),
        port=os.getenv("PG_PORT"),
    )


def test_establish_and_delete_coalition_db_roundtrip():
    """Integration test: create a coalition row, verify it exists, then delete it.

    This test is skipped by default; set RUN_DB_INTEGRATION=1 to enable it.
    """
    if os.getenv("RUN_DB_INTEGRATION") != "1":
        pytest.skip("Database integration tests not enabled")

    c_name = f"test_coalition_{int(time.time())}"
    conn = _connect_db()
    cur = conn.cursor()

    try:
        cur.execute(
            (
                "INSERT INTO colNames (name, type, description, date) "
                "VALUES (%s, %s, %s, %s) RETURNING id"
            ),
            (c_name, "Open", "Integration test coalition", str(time.time())),
        )
        created = cur.fetchone()[0]
        conn.commit()

        cur.execute("SELECT name FROM colNames WHERE id=%s", (created,))
        name = cur.fetchone()[0]
        assert name == c_name

    finally:
        # Clean up
        cur.execute("DELETE FROM colNames WHERE id=%s", (created,))
        conn.commit()
        cur.close()
        conn.close()
