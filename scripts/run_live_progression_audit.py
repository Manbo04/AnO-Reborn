#!/usr/bin/env python3
"""
Run full live progression audit (DB + static + optional HTTP).

Usage:
  DATABASE_PUBLIC_URL=... python3 scripts/run_live_progression_audit.py
  DATABASE_PUBLIC_URL=... python3 scripts/run_live_progression_audit.py --http
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TEST_UID = 16
PROD = "https://affairsandorder.com"


def _run(cmd: list[str]) -> int:
    print("\n>>>", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=ROOT, env=os.environ.copy())
    return proc.returncode


def _audit_user16():
    from database import get_db_connection
    from tasks import food_stats, rations_distribution_capacity, rations_needed

    import variables

    print(f"\n=== Account {TEST_UID} progression signals ===")
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT username FROM users WHERE id=%s", (TEST_UID,))
        row = db.fetchone()
        if not row:
            print(f"User {TEST_UID} not found")
            return
        print(f"Username: {row[0]}")
        db.execute("SELECT gold FROM stats WHERE id=%s", (TEST_UID,))
        print(f"Gold: {db.fetchone()[0]:,}")
        db.execute(
            "SELECT COUNT(*), COALESCE(SUM(population),0) FROM provinces WHERE userid=%s",
            (TEST_UID,),
        )
        n_prov, pop = db.fetchone()
        print(f"Provinces: {n_prov}, population: {pop:,}")

    cap = rations_distribution_capacity(TEST_UID)
    need = rations_needed(TEST_UID)
    food = food_stats(TEST_UID)
    print(f"Rations needed (tick units): {need}")
    print(f"Distribution capacity: {cap:,}")
    print(f"Food score: {food} (<0 = bottleneck despite stockpile)")
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            "SELECT COALESCE(SUM(population),0) FROM provinces WHERE userid=%s",
            (TEST_UID,),
        )
        pop = db.fetchone()[0]
    if pop and cap < pop:
        print(f"P2: distribution covers {cap/pop*100:.1f}% of population")

    caps = variables.RATIONS_DISTRIBUTION_PER_BUILDING
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            """
            SELECT bd.name, SUM(ub.quantity)::int
            FROM user_buildings ub
            JOIN building_dictionary bd ON bd.building_id = ub.building_id
            WHERE ub.user_id = %s AND bd.name = ANY(%s)
            GROUP BY bd.name
            """,
            (TEST_UID, list(caps.keys())),
        )
        print("Distribution buildings:")
        for name, q in db.fetchall():
            print(f"  {name}: {q}")


def _http_smoke():
    import urllib.request

    paths = [
        f"/country/id={TEST_UID}",
        "/countries",
        "/coalitions",
        "/market",
        "/tutorial",
        "/signup",
    ]
    print("\n=== Production HTTP ===")
    for path in paths:
        url = PROD + path
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=15) as resp:
                code = resp.status
        except Exception as e:
            code = str(e)
        print(f"  {code:>4} {url}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--http", action="store_true", help="HEAD requests to production")
    args = parser.parse_args()

    if not (os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")):
        print("ERROR: set DATABASE_PUBLIC_URL")
        return 1

    rc = 0
    rc |= _run([sys.executable, "scripts/progression_balance_audit.py"])
    rc |= _run([sys.executable, "scripts/progression_health_check.py"])
    _audit_user16()
    if args.http:
        _http_smoke()
    return min(rc, 1)


if __name__ == "__main__":
    sys.exit(main())
