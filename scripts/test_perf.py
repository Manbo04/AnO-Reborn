#!/usr/bin/env python3
"""Test page load performance to identify bottlenecks."""

import os
import time
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TEST_UID = int(os.getenv("PROGRESSION_TEST_UID", "16"))

start = time.time()
from database import get_db_cursor  # noqa: E402

print(f"Import database: {time.time() - start:.3f}s")

# Test basic query
t1 = time.time()
with get_db_cursor() as db:
    db.execute("SELECT 1")
    db.fetchone()
print(f"First query (pool init): {time.time() - t1:.3f}s")

t2 = time.time()
with get_db_cursor() as db:
    db.execute("SELECT 1")
    db.fetchone()
print(f"Second query (pooled): {time.time() - t2:.3f}s")

# Test country query
t3 = time.time()
with get_db_cursor() as db:
    db.execute(
        """
        SELECT u.username, s.location, u.description, u.date, u.flag,
               c.colId, c.role, cn.name, cn.flag
        FROM users u
        INNER JOIN stats s ON u.id=s.id
        LEFT JOIN coalitions c ON u.id=c.userId
        LEFT JOIN colNames cn ON c.colId=cn.id
        WHERE u.id=%s
    """,
        (TEST_UID,),
    )
    row = db.fetchone()
print(f"Country main query (uid={TEST_UID}): {time.time() - t3:.3f}s")

t4 = time.time()
with get_db_cursor() as db:
    db.execute(
        "SELECT SUM(population), AVG(happiness), COUNT(id) "
        "FROM provinces WHERE userId=%s",
        (TEST_UID,),
    )
    db.fetchone()
print(f"Province stats query: {time.time() - t4:.3f}s")

t5 = time.time()
try:
    from countries import get_revenue

    get_revenue(TEST_UID)
    print(f"get_revenue(uid={TEST_UID}): {time.time() - t5:.3f}s")
except Exception as e:
    print(f"get_revenue() failed: {e}")

t6 = time.time()
try:
    from helpers import get_influence

    get_influence(TEST_UID)
    print(f"get_influence(): {time.time() - t6:.3f}s")
except Exception as e:
    print(f"get_influence() failed: {e}")

t7 = time.time()
try:
    from tasks import rations_needed

    rations_needed(TEST_UID)
    print(f"rations_needed(): {time.time() - t7:.3f}s")
except Exception as e:
    print(f"rations_needed() failed: {e}")

t8 = time.time()
try:
    from countries import get_econ_statistics

    get_econ_statistics(TEST_UID)
    print(f"get_econ_statistics(): {time.time() - t8:.3f}s")
except Exception as e:
    print(f"get_econ_statistics() failed: {e}")

print(f"\nTotal test time: {time.time() - start:.3f}s")
