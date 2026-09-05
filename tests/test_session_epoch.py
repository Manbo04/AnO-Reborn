"""Tests for real session invalidation via users.session_epoch.

Regression coverage for the incident described in migration 0068:
admin_user_controls.kick_pending is a one-shot flag, cached per-session in
app.py's before_request for up to ADMIN_CTRL_REFRESH_SECONDS. If a user has
two concurrent sessions (e.g. a stolen/leaked cookie alongside their real
browser), whichever session polls the DB first flips kick_pending back to
FALSE, so only that one session actually gets logged out -- the other rides
on indefinitely. session_epoch is monotonic DB state instead: bumping it
must force out *every* session carrying an older embedded value, not just
the first one to check.
"""
import uuid

import bcrypt
import pytest

from database import get_db_cursor, bump_session_epoch, set_user_password
from app_core.admin.services import process_kick_user, process_ban_user

TEST_PASSWORD = "correct-horse-battery"


@pytest.fixture
def client():
    from app import app

    with app.test_client() as c:
        yield c


def _create_user():
    with get_db_cursor() as db:
        username = f"epoch_{uuid.uuid4().hex[:8]}"
        email = f"{username}@example.invalid"
        hashed = bcrypt.hashpw(TEST_PASSWORD.encode("utf-8"), bcrypt.gensalt(4)).decode("utf-8")
        db.execute(
            (
                "INSERT INTO users (username, email, hash, date, auth_type) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id"
            ),
            (username, email, hashed, "1970-01-01", "normal"),
        )
        user_id = db.fetchone()[0]
    return user_id


def _get_epoch(user_id):
    with get_db_cursor() as db:
        db.execute("SELECT session_epoch FROM users WHERE id=%s", (user_id,))
        return db.fetchone()[0]


def _force_ctrl_cache_stale(client):
    """Simulate the ADMIN_CTRL_REFRESH_SECONDS window having elapsed, so the
    next request re-checks live DB state instead of trusting whatever was
    cached into the session by a prior request."""
    with client.session_transaction() as sess:
        sess["_admin_ctrl_ts"] = 0


# --- bump_session_epoch plumbing -------------------------------------------------


def test_bump_session_epoch_increments():
    user_id = _create_user()
    before = _get_epoch(user_id)
    with get_db_cursor() as db:
        bump_session_epoch(db, user_id)
    assert _get_epoch(user_id) == before + 1


def test_password_change_bumps_epoch():
    """A password change is supposed to be the standard 'lock everyone else
    out' move -- set_user_password must bump session_epoch too."""
    user_id = _create_user()
    before = _get_epoch(user_id)
    new_hash = bcrypt.hashpw(b"new-password-123", bcrypt.gensalt(4)).decode("utf-8")
    with get_db_cursor() as db:
        set_user_password(db, user_id, new_hash)
    assert _get_epoch(user_id) == before + 1


def test_admin_kick_bumps_epoch():
    from app import app

    user_id = _create_user()
    before = _get_epoch(user_id)
    with app.test_request_context():
        err = process_kick_user(actor=1, target_user_id=user_id, reason="test kick")
    assert err is None
    assert _get_epoch(user_id) == before + 1


def test_admin_ban_bumps_epoch():
    from app import app

    user_id = _create_user()
    before = _get_epoch(user_id)
    with app.test_request_context():
        err = process_ban_user(actor=1, target_user_id=user_id, reason="test ban")
    assert err is None
    assert _get_epoch(user_id) == before + 1


# --- end-to-end: before_request actually enforces it -----------------------------


def test_fresh_session_survives_request(client):
    user_id = _create_user()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["session_epoch"] = _get_epoch(user_id)

    resp = client.get("/account")
    assert resp.status_code == 200


def test_stale_epoch_session_is_kicked_to_login(client):
    """The core regression: bump the DB epoch out from under a live session
    and confirm the *next* checked request is force-logged-out, not left
    alone the way a consumed kick_pending flag would leave it."""
    user_id = _create_user()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["session_epoch"] = _get_epoch(user_id)

    # Prime the request so it's accepted once, matching current epoch.
    resp = client.get("/account")
    assert resp.status_code == 200

    # Simulate an admin kick sometime later.
    from app import app as _app

    with _app.test_request_context():
        process_kick_user(actor=1, target_user_id=user_id, reason="stale test")

    # Force the cached admin-controls check to be treated as stale so this
    # next request actually re-reads the DB (mirrors ADMIN_CTRL_REFRESH_SECONDS
    # elapsing in real usage).
    _force_ctrl_cache_stale(client)

    resp = client.get("/account", follow_redirects=False)
    assert resp.status_code in (302, 303)
    assert resp.headers.get("Location", "").rstrip("/").endswith("/login")

    # The session should have been cleared server-side too.
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_epoch_bump_kicks_every_concurrent_session():
    """Regression test for the exact incident this migration fixes: TWO
    concurrent sessions for the same account (e.g. the real browser + a
    leaked/stolen cookie). A single kick/ban must invalidate BOTH, not just
    whichever one happens to poll the DB first."""
    from app import app

    user_id = _create_user()
    epoch_at_login = _get_epoch(user_id)

    client_a = app.test_client()
    client_b = app.test_client()

    for c in (client_a, client_b):
        with c.session_transaction() as sess:
            sess["user_id"] = user_id
            sess["session_epoch"] = epoch_at_login
        # Prime each session as accepted once.
        resp = c.get("/account")
        assert resp.status_code == 200

    # A single admin kick action bumps the epoch once.
    with app.test_request_context():
        err = process_kick_user(actor=1, target_user_id=user_id, reason="dual session test")
    assert err is None

    # Both sessions' caches are simulated as stale independently (in
    # production this just means both eventually cross the
    # ADMIN_CTRL_REFRESH_SECONDS window -- not simultaneously, and not
    # necessarily in any particular order).
    for c in (client_b, client_a):
        _force_ctrl_cache_stale(c)
        resp = c.get("/account", follow_redirects=False)
        assert resp.status_code in (302, 303), (
            "concurrent session was not invalidated by the kick -- this is "
            "exactly the bug kick_pending had (only the first poller got "
            "logged out)"
        )
        assert resp.headers.get("Location", "").rstrip("/").endswith("/login")


def test_session_without_embedded_epoch_defaults_to_zero(client):
    """Sessions issued before this feature existed have no 'session_epoch'
    key at all. They must NOT be mass-logged-out on deploy -- the column
    defaults new/existing users to 0, so a missing session key should be
    treated as epoch 0 and compared normally."""
    user_id = _create_user()
    assert _get_epoch(user_id) == 0

    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        # Deliberately do NOT set sess["session_epoch"] here.

    resp = client.get("/account")
    assert resp.status_code == 200
