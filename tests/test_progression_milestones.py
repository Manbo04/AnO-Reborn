"""
DB-backed progression milestones for test account 16 (Tester of the Game).

Snapshots and restores user state — LEAVE NO TRACE.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

TEST_USER_ID = 16
ROOT = Path(__file__).resolve().parents[1]


def _db_available_user16():
    if not os.getenv("DATABASE_PUBLIC_URL") and not os.getenv("DATABASE_URL"):
        return False
    try:
        from database import get_db_connection

        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute("SELECT id FROM users WHERE id=%s", (TEST_USER_ID,))
            return db.fetchone() is not None
    except Exception:
        return False


requires_db = pytest.mark.skipif(
    not os.getenv("DATABASE_PUBLIC_URL") and not os.getenv("DATABASE_URL"),
    reason="Requires Postgres (DATABASE_PUBLIC_URL or DATABASE_URL)",
)
requires_user16 = pytest.mark.skipif(
    not _db_available_user16(),
    reason=f"Test user {TEST_USER_ID} not found in database",
)


def snapshot_user_state():
    """Return JSON-serializable snapshot for restore."""
    from database import get_db_connection

    snap: dict = {"user_id": TEST_USER_ID, "stats": None, "economy": [], "buildings": []}
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT gold, location FROM stats WHERE id=%s", (TEST_USER_ID,))
        row = db.fetchone()
        if row:
            snap["stats"] = {"gold": row[0], "location": row[1]}

        db.execute(
            """
            SELECT ue.resource_id, ue.quantity, rd.name
            FROM user_economy ue
            JOIN resource_dictionary rd ON rd.resource_id = ue.resource_id
            WHERE ue.user_id = %s
            """,
            (TEST_USER_ID,),
        )
        snap["economy"] = [
            {"resource_id": r[0], "quantity": r[1], "name": r[2]} for r in db.fetchall()
        ]

        db.execute(
            """
            SELECT ub.province_id, ub.building_id, ub.quantity, bd.name
            FROM user_buildings ub
            JOIN building_dictionary bd ON bd.building_id = ub.building_id
            WHERE ub.user_id = %s
            """,
            (TEST_USER_ID,),
        )
        snap["buildings"] = [
            {
                "province_id": r[0],
                "building_id": r[1],
                "quantity": r[2],
                "name": r[3],
            }
            for r in db.fetchall()
        ]
    return snap


def restore_user_state(snap: dict):
    from database import get_db_connection

    with get_db_connection() as conn:
        db = conn.cursor()
        if snap.get("stats"):
            db.execute(
                "UPDATE stats SET gold=%s, location=%s WHERE id=%s",
                (snap["stats"]["gold"], snap["stats"]["location"], TEST_USER_ID),
            )
        for row in snap.get("economy", []):
            db.execute(
                """
                INSERT INTO user_economy (user_id, resource_id, quantity)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, resource_id)
                DO UPDATE SET quantity = EXCLUDED.quantity
                """,
                (TEST_USER_ID, row["resource_id"], row["quantity"]),
            )
        db.execute(
            "DELETE FROM user_buildings WHERE user_id = %s",
            (TEST_USER_ID,),
        )
        for row in snap.get("buildings", []):
            db.execute(
                """
                INSERT INTO user_buildings
                    (user_id, building_id, province_id, quantity)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id, building_id, province_id)
                DO UPDATE SET quantity = EXCLUDED.quantity
                """,
                (
                    TEST_USER_ID,
                    row["building_id"],
                    row["province_id"],
                    row["quantity"],
                ),
            )
        conn.commit()


def test_progression_balance_audit_script_exits_zero():
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts/progression_balance_audit.py")],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PROGRESSION BALANCE AUDIT" in proc.stdout


def test_gas_station_price_matches_variables():
    import variables

    assert variables.PROVINCE_UNIT_PRICES["gas_stations_price"] == 7_000_000


def test_production_country_page_200():
    """Smoke production country page without importing Flask (avoids jinja2 pin issues)."""
    import urllib.error
    import urllib.request

    base = os.getenv("PROD_URL", "https://affairsandorder.com").rstrip("/")
    url = f"{base}/country/id={TEST_USER_ID}"
    req = urllib.request.Request(
        url,
        method="GET",
        headers={"User-Agent": "AnO-Progression-Audit/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            code = resp.status
            body = resp.read(500).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        code = e.code
        body = e.read(200).decode("utf-8", errors="replace")
    assert code == 200, f"{url} returned {code}"
    assert "Invalid Server Error" not in body


@requires_db
@requires_user16
def test_revenue_task_updates_resources_or_gold():
    """One revenue + tax pass must change economy or gold when buildings exist."""
    import tasks

    snap = snapshot_user_state()
    try:
        from database import get_db_connection

        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute(
                """
                UPDATE task_runs SET last_run = now() - interval '2 days'
                WHERE task_name IN (
                    'generate_province_revenue', 'tax_income', 'population_growth'
                )
                """
            )
            conn.commit()

        before = {r["name"]: r["quantity"] for r in snap["economy"]}
        before_gold = (snap.get("stats") or {}).get("gold")

        tasks.generate_province_revenue()
        tasks.tax_income()

        after_snap = snapshot_user_state()
        after = {r["name"]: r["quantity"] for r in after_snap["economy"]}
        after_gold = (after_snap.get("stats") or {}).get("gold")

        changed = any(before.get(k) != after.get(k) for k in set(before) | set(after))
        gold_changed = before_gold != after_gold
        # Nation may have zero buildings — allow skip assertion only if no buildings
        if snap.get("buildings"):
            assert changed or gold_changed, (
                "Expected resource or gold change after tasks with buildings"
            )
    finally:
        restore_user_state(snap)


@requires_db
def test_rations_high_without_distribution_blocks_food_score():
    """High stockpile + zero distribution capacity => poor food score."""
    import uuid

    import variables
    from tasks import food_stats, rations_distribution_capacity

    variables.FEATURE_RATIONS_DISTRIBUTION = True

    from database import get_db_connection

    uid = None
    pid = None
    try:
        with get_db_connection() as conn:
            db = conn.cursor()
            name = f"prog_{uuid.uuid4().hex[:8]}"
            db.execute(
                "INSERT INTO users (username, email, date, hash) "
                "VALUES (%s,%s,%s,%s) RETURNING id",
                (name, f"{name}@test.local", "2026-05-22", ""),
            )
            uid = db.fetchone()[0]
            db.execute(
                "INSERT INTO stats (id, location, gold) VALUES (%s,%s,%s)",
                (uid, "T", 1_000_000),
            )
            db.execute(
                "INSERT INTO provinces (userId, provincename, population, land, citycount) "
                "VALUES (%s,%s,%s,%s,%s) RETURNING id",
                (uid, "prog_test", 500_000, 1, 1),
            )
            pid = db.fetchone()[0]
            # Ensure economy row for rations
            db.execute("SELECT resource_id FROM resource_dictionary WHERE name='rations'")
            rid = db.fetchone()[0]
            db.execute(
                """
                INSERT INTO user_economy (user_id, resource_id, quantity)
                VALUES (%s,%s,%s)
                ON CONFLICT (user_id, resource_id) DO UPDATE SET quantity = EXCLUDED.quantity
                """,
                (uid, rid, 1_000_000),
            )
            conn.commit()

        assert rations_distribution_capacity(uid) == 0
        assert food_stats(uid) < -1

    finally:
        if uid and pid:
            with get_db_connection() as conn:
                db = conn.cursor()
                db.execute("DELETE FROM user_economy WHERE user_id=%s", (uid,))
                db.execute("DELETE FROM provinces WHERE id=%s", (pid,))
                db.execute("DELETE FROM stats WHERE id=%s", (uid,))
                db.execute("DELETE FROM users WHERE id=%s", (uid,))
                conn.commit()


@requires_db
@requires_user16
def test_snapshot_roundtrip_preserves_gold():
    snap = snapshot_user_state()
    try:
        from database import get_db_connection

        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute(
                "UPDATE stats SET gold = gold + 1 WHERE id = %s",
                (TEST_USER_ID,),
            )
            conn.commit()
        restore_user_state(snap)
        again = snapshot_user_state()
        assert again.get("stats", {}).get("gold") == snap.get("stats", {}).get("gold")
    finally:
        restore_user_state(snap)
