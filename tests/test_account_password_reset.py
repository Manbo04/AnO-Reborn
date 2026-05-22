"""Tests for logged-in account password reset (Discord DM + direct link)."""
import uuid
from unittest.mock import patch

import pytest

from database import get_db_cursor


@pytest.fixture
def client():
    from app import app

    with app.test_client() as c:
        yield c


def _create_user():
    with get_db_cursor() as db:
        username = f"pwreset_{uuid.uuid4().hex[:8]}"
        email = f"{username}@example.invalid"
        db.execute(
            (
                "INSERT INTO users (username, email, hash, date, auth_type) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id"
            ),
            (username, email, "x", "1970-01-01", "normal"),
        )
        user_id = db.fetchone()[0]
    return user_id


def test_logged_in_reset_redirects_to_reset_page(client):
    user_id = _create_user()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    resp = client.post("/request_password_reset", follow_redirects=False)
    assert resp.status_code in (302, 303)
    assert "/reset_password/" in resp.headers.get("Location", "")


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

    resp = client.post("/request_password_reset", follow_redirects=True)
    assert resp.status_code == 200
    mock_dm.assert_called_once()
    assert b"Discord DMs" in resp.data
