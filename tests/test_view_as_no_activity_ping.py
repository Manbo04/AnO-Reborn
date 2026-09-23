"""Regression test found 2026-09-23 during the admin-panel security
re-audit: admin "view as" (app_core/admin/routes.py::admin_view_as) swaps
session["user_id"] to the target player and only blocks non-GET
requests. app.py's before_request activity ping still ran on those GETs
as the target -- updating their last_active ("online now") and calling
process_referral_activity(), which records a referral active day for
them and can pay their inviter a milestone reward the player never
earned. The ping is now skipped while _real_admin_id is set.

Runs against the real local ano_staging database.
"""
import uuid
from datetime import date
from time import time

import bcrypt
import pytest

from database import get_db_connection

TEST_PASSWORD = bcrypt.hashpw(b"correct-horse-battery", bcrypt.gensalt()).decode()


@pytest.fixture
def target_user():
    with get_db_connection() as conn:
        db = conn.cursor()
        username = f"viewas_{uuid.uuid4().hex[:8]}"
        db.execute(
            """
            INSERT INTO users (username, email, date, hash, auth_type, last_active)
            VALUES (%s, %s, '2026-09-23', %s, 'normal', '2020-01-01')
            RETURNING id
            """,
            (username, f"{username}@example.com", TEST_PASSWORD),
        )
        user_id = db.fetchone()[0]
        db.execute(
            "INSERT INTO stats (id, location, gold) VALUES (%s, 'Tundra', 0)",
            (user_id,),
        )
        conn.commit()

    yield user_id

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("DELETE FROM referral_active_days WHERE referred_user_id = %s", (user_id,))
        db.execute("DELETE FROM user_economy WHERE user_id = %s", (user_id,))
        db.execute("DELETE FROM stats WHERE id = %s", (user_id,))
        db.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()


def test_view_as_get_does_not_ping_activity_as_target(target_user):
    from app import app

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = target_user
        sess["_real_admin_id"] = 1
        sess["_view_as_started_at"] = time()
        sess["_view_as_reason"] = "regression test"

    client.get("/")

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT last_active FROM users WHERE id = %s", (target_user,))
        last_active = db.fetchone()[0]
        db.execute(
            "SELECT to_regclass('referral_active_days') IS NOT NULL"
        )
        has_table = db.fetchone()[0]
        active_days = 0
        if has_table:
            db.execute(
                """
                SELECT COUNT(*) FROM referral_active_days
                WHERE referred_user_id = %s AND activity_date = %s
                """,
                (target_user, date.today()),
            )
            active_days = db.fetchone()[0]

    assert last_active.year == 2020, (
        f"target's last_active was bumped to {last_active} by an admin view-as GET"
    )
    assert active_days == 0, "admin view-as recorded a referral active day for the target"
