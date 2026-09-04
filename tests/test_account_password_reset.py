"""Tests for logged-in account password reset (Discord DM + direct link).

Following ticket-0028 (2026-09-04): a stray/leaked session used to be enough
to pull a working reset code for whatever account that session belonged to,
via the *public* /request_password_reset endpoint -- see
test_public_reset_ignores_ambient_session below for the regression test.
The logged-in flow now lives at /account/request_password_reset and
additionally requires the current password.
"""
import uuid
from unittest.mock import patch

import bcrypt
import pytest

from database import get_db_cursor

TEST_PASSWORD = "correct-horse-battery"


@pytest.fixture
def client():
    from app import app

    with app.test_client() as c:
        yield c


def _create_user():
    with get_db_cursor() as db:
        username = f"pwreset_{uuid.uuid4().hex[:8]}"
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


def test_logged_in_reset_redirects_to_reset_page(client):
    user_id = _create_user()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    resp = client.post(
        "/account/request_password_reset",
        data={"current_password": TEST_PASSWORD},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)
    assert "/reset_password/" in resp.headers.get("Location", "")


def test_logged_in_reset_requires_correct_current_password(client):
    user_id = _create_user()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    resp = client.post(
        "/account/request_password_reset",
        data={"current_password": "not the right password"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Incorrect password" in resp.data


def test_logged_in_reset_requires_login(client):
    resp = client.post(
        "/account/request_password_reset",
        data={"current_password": TEST_PASSWORD},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)
    assert "/reset_password/" not in resp.headers.get("Location", "")


@patch("change.send_discord_password_reset_dm", return_value=True)
def test_logged_in_reset_sends_discord_dm(mock_dm, client):
    user_id = _create_user()
    discord_id = "123456789012345678"
    with get_db_cursor() as db:
        try:
            db.execute(
                "UPDATE users SET discord_id=%s WHERE id=%s",
                (discord_id, user_id),
            )
        except Exception:
            pytest.skip("discord_id column not available")

    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    resp = client.post(
        "/account/request_password_reset",
        data={"current_password": TEST_PASSWORD},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    mock_dm.assert_called_once()
    assert b"Discord DMs" in resp.data


def test_public_reset_ignores_ambient_session(client):
    """Regression test for ticket-0028: a visitor whose browser happens to
    carry a session for account A, but who submits account B's email to the
    public /forgot_password form, must get a reset code for B -- never A."""
    victim_id = _create_user()
    target_id = _create_user()

    with get_db_cursor() as db:
        db.execute("SELECT email FROM users WHERE id=%s", (target_id,))
        target_email = db.fetchone()[0]

    with client.session_transaction() as sess:
        sess["user_id"] = victim_id

    resp = client.post(
        "/request_password_reset",
        data={"email": target_email},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)
    assert resp.headers.get("Location", "") == "/forgot_password"

    with get_db_cursor() as db:
        db.execute("SELECT user_id FROM reset_codes WHERE user_id=%s", (target_id,))
        assert db.fetchone() is not None
        db.execute("SELECT user_id FROM reset_codes WHERE user_id=%s", (victim_id,))
        assert db.fetchone() is None
