"""Regression test for a candidate root cause of the account
cross-contamination reports investigated 2026-09-12 but never confirmed
(found 2026-09-15 during an architecture audit).

signup.py's discord_register()/signup()/verify_email(), google_auth.py's
google_signup_route(), and email_auth.py's register_email() each set
session["user_id"] directly after creating a brand-new account, without
clearing the session first -- unlike their own login-branch counterparts,
which already correctly funneled through complete_or_verify_login(). A
stale session left over from a previous account (or an in-progress
OAuth/2FA flow) on the same browser could therefore merge into the new
account instead of starting clean. The fix extracts the shared
session-establishment logic into establish_authenticated_session() and
has every account-creation branch call it too.
"""
import uuid

import bcrypt
import pytest
from flask import session

pytestmark = pytest.mark.no_server

TEST_PASSWORD = "correct-horse-battery"


def _create_user():
    from database import get_db_cursor

    with get_db_cursor() as db:
        username = f"xcontam_{uuid.uuid4().hex[:8]}"
        email = f"{username}@example.invalid"
        hashed = bcrypt.hashpw(TEST_PASSWORD.encode("utf-8"), bcrypt.gensalt(4)).decode("utf-8")
        db.execute(
            (
                "INSERT INTO users (username, email, hash, date, auth_type) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id"
            ),
            (username, email, hashed, "1970-01-01", "normal"),
        )
        return db.fetchone()[0]


def test_establish_authenticated_session_clears_stale_session_data():
    from app import app
    from login_verification import establish_authenticated_session

    old_user_id = _create_user()
    new_user_id = _create_user()

    with app.test_request_context():
        session["user_id"] = old_user_id
        session["google_oauth2_state"] = "leftover-from-a-different-flow"
        session["pending_2fa_user_id"] = old_user_id
        session["pending_recovery_key"] = "should-not-survive-either"

        establish_authenticated_session(new_user_id, "203.0.113.5", "test-fp", "password")

        assert session["user_id"] == new_user_id
        assert "google_oauth2_state" not in session
        assert "pending_2fa_user_id" not in session
        assert "pending_recovery_key" not in session
        # The new session must still get the epoch/permanence bookkeeping
        # complete_or_verify_login() always set, not a stripped-down version.
        assert session.permanent is True
        assert "session_epoch" in session


def test_establish_authenticated_session_logs_a_login_event():
    """Signup paths previously set the session directly and (mostly) skipped
    log_login_event entirely, leaving no forensic trail for a brand-new
    account's first-ever login."""
    from app import app
    from database import get_db_cursor
    from login_verification import establish_authenticated_session

    user_id = _create_user()

    with app.test_request_context():
        establish_authenticated_session(user_id, "203.0.113.7", "test-fp", "discord")

    with get_db_cursor() as db:
        db.execute(
            "SELECT auth_type FROM login_events WHERE user_id=%s ORDER BY id DESC LIMIT 1",
            (user_id,),
        )
        row = db.fetchone()
    assert row is not None
    assert row[0] == "discord"


def test_signup_completion_paths_no_longer_set_session_directly():
    """Static guard against regressing back to the direct-assignment bug:
    none of the account-creation branches should set session["user_id"]
    themselves anymore -- they should all route through
    establish_authenticated_session (or complete_or_verify_login) instead."""
    import re

    for path in (
        "signup.py",
        "app_core/auth/google_auth.py",
        "app_core/auth/email_auth.py",
    ):
        with open(path, encoding="utf-8") as f:
            src = f.read()
        assert not re.search(r'session\["user_id"\]\s*=\s*\w', src), (
            f"{path} sets session['user_id'] directly again -- route it "
            "through establish_authenticated_session() instead"
        )
