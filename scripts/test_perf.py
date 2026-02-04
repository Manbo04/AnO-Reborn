#!/usr/bin/env python3
"""Test page load performance to identify bottlenecks."""
import time
import sys

sys.path.insert(0, "/Users/dede/AnO")

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
        WHERE u.id=1
    """
    )
    row = db.fetchone()
print(f"Country main query: {time.time() - t3:.3f}s")

# Test provinces query
t4 = time.time()
with get_db_cursor() as db:
    db.execute(
        "SELECT SUM(population), AVG(happiness), COUNT(id) "
        "FROM provinces WHERE userId=1"
    )
    db.fetchone()
print(f"Province stats query: {time.time() - t4:.3f}s")

# Test get_revenue (often slow)
t5 = time.time()
try:
    from countries import get_revenue

    rev = get_revenue(1)
    print(f"get_revenue(): {time.time() - t5:.3f}s")
except Exception as e:
    print(f"get_revenue() failed: {e}")

# Test get_influence
t6 = time.time()
try:
    from helpers import get_influence

    inf = get_influence(1)
    print(f"get_influence(): {time.time() - t6:.3f}s")
except Exception as e:
    print(f"get_influence() failed: {e}")

# Test rations_needed
t7 = time.time()
try:
    from tasks import rations_needed

    rn = rations_needed(1)
    print(f"rations_needed(): {time.time() - t7:.3f}s")
except Exception as e:
    print(f"rations_needed() failed: {e}")

# Test get_econ_statistics
t8 = time.time()
try:
    from countries import get_econ_statistics

    stats = get_econ_statistics(1)
    print(f"get_econ_statistics(): {time.time() - t8:.3f}s")
except Exception as e:
    print(f"get_econ_statistics() failed: {e}")

print(f"\nTotal test time: {time.time() - start:.3f}s")
