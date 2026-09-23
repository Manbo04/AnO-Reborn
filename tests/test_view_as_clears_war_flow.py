"""Regression test found 2026-09-23 during the admin-panel security
re-audit: /warResult resolves a staged attack on a plain GET from
session state (attack_units / enemy_id / war_domain / from_wartarget),
and admin "view as" only blocks non-GET requests. An attack an admin had
staged as themselves survived into view-as, so a GET /warResult would
resolve it with session["user_id"] = the viewed player -- a write made
as someone else while impersonating. view-as start, explicit exit and
before_request auto-expiry now all drop that state.

Calls the real route functions directly inside test_request_context
(auth/target validation stubbed -- they're covered elsewhere); the
auto-expiry case goes through the real before_request.
"""
import uuid
from time import time

import pytest

from database import get_db_connection

WAR_KEYS = ("attack_units", "enemy_id", "war_domain", "from_wartarget")


def _stage_attack(sess):
    sess["attack_units"] = {"soldiers": 100}
    sess["enemy_id"] = 999
    sess["war_domain"] = "ground"
    sess["from_wartarget"] = True


def test_view_as_start_drops_staged_attack(monkeypatch):
    from app import app
    import app_core.admin.routes as admin_routes

    monkeypatch.setattr(admin_routes, "admin_only_guard", lambda _uid: None)
    monkeypatch.setattr(admin_routes, "process_start_view_as", lambda *a: None)

    with app.test_request_context(
        "/admin/command-center/view-as",
        method="POST",
        data={"target_user_id": "4242", "reason": "support ticket"},
    ):
        from flask import session

        session["user_id"] = 1
        _stage_attack(session)
        admin_routes.admin_view_as.__wrapped__()
        assert session["user_id"] == 4242
        leftover = [k for k in WAR_KEYS if k in session]

    assert not leftover, f"staged attack state survived into view-as: {leftover}"


def test_view_as_exit_drops_staged_attack(monkeypatch):
    from app import app
    import app_core.admin.routes as admin_routes

    monkeypatch.setattr(admin_routes, "finish_view_as", lambda *a, **k: None)

    with app.test_request_context("/admin/view-as/exit", method="POST"):
        from flask import session

        session["user_id"] = 4242
        session["_real_admin_id"] = 1
        session["_view_as_started_at"] = time()
        _stage_attack(session)
        admin_routes.admin_view_as_exit.__wrapped__()
        assert session["user_id"] == 1
        leftover = [k for k in WAR_KEYS if k in session]

    assert not leftover, f"view-as war state survived back into the admin session: {leftover}"


@pytest.fixture
def real_admin_user():
    # Must be a real row: before_request's session_epoch check clears the
    # whole session for a nonexistent user_id, which would make the
    # auto-expiry assertion pass trivially.
    with get_db_connection() as conn:
        db = conn.cursor()
        username = f"viewaswar_{uuid.uuid4().hex[:8]}"
        db.execute(
            """
            INSERT INTO users (username, email, date, hash, auth_type)
            VALUES (%s, %s, '2026-09-23', 'x', 'normal')
            RETURNING id
            """,
            (username, f"{username}@example.com"),
        )
        user_id = db.fetchone()[0]
        conn.commit()

    yield user_id

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()


def test_view_as_auto_expiry_drops_staged_attack(monkeypatch, real_admin_user):
    from app import app
    import app_core.admin.services as admin_services

    monkeypatch.setattr(admin_services, "finish_view_as", lambda *a, **k: None)

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = 4242
        sess["_real_admin_id"] = real_admin_user
        sess["_view_as_started_at"] = time() - admin_services.VIEW_AS_MAX_SECONDS - 60
        _stage_attack(sess)

    client.get("/")

    with client.session_transaction() as sess:
        assert sess.get("user_id") == real_admin_user, "session was cleared, not expired back to the admin"
        assert "_real_admin_id" not in sess
        leftover = [k for k in WAR_KEYS if k in sess]

    assert not leftover, f"view-as war state survived auto-expiry: {leftover}"
