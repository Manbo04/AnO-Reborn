"""Tests for backup recovery key generation and reset flow."""
import uuid

import bcrypt
import pytest

from database import get_db_cursor, users_table_has_column


@pytest.fixture
def client():
    from app import app

    with app.test_client() as c:
        yield c


def _recovery_key_column_available() -> bool:
    try:
        return users_table_has_column("recovery_key")
    except Exception:
        return False


def _create_user(username_suffix: str | None = None, with_key: bool = False):
    suffix = username_suffix or uuid.uuid4().hex[:8]
    username = f"rk_{suffix}"
    email = f"{username}@example.invalid"
    recovery_key = None
    if with_key:
        raw = "testkey12345678"
        recovery_key = bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt(4)).decode("utf-8")

    with get_db_cursor() as db:
        if recovery_key is not None and _recovery_key_column_available():
            db.execute(
                (
                    "INSERT INTO users (username, email, hash, date, auth_type, recovery_key) "
                    "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id"
                ),
                (username, email, "x", "1970-01-01", "normal", recovery_key),
            )
        else:
            db.execute(
                (
                    "INSERT INTO users (username, email, hash, date, auth_type) "
                    "VALUES (%s, %s, %s, %s, %s) RETURNING id"
                ),
                (username, email, "x", "1970-01-01", "normal"),
            )
        user_id = db.fetchone()[0]
    return user_id, username, email, "testkey12345678" if with_key else None


@pytest.mark.skipif(
    not _recovery_key_column_available(),
    reason="recovery_key column not available",
)
def test_user_without_key_gets_safe_message(client):
    _, username, _, _ = _create_user(with_key=False)

    resp = client.post(
        "/reset_password_recovery_key",
        data={"username": username, "recovery_key": "anything"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"No recovery key on file" in resp.data


@pytest.mark.skipif(
    not _recovery_key_column_available(),
    reason="recovery_key column not available",
)
def test_user_with_key_can_reset_and_key_is_wiped(client):
    user_id, username, _, raw_key = _create_user(with_key=True)

    resp = client.post(
        "/reset_password_recovery_key",
        data={"username": username, "recovery_key": raw_key},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)
    assert "/discord_reset_password_page" in resp.headers.get("Location", "")

    with get_db_cursor() as db:
        db.execute("SELECT recovery_key FROM users WHERE id=%s", (user_id,))
        row = db.fetchone()
        assert row is not None
        assert row[0] is None


@pytest.mark.skipif(
    not _recovery_key_column_available(),
    reason="recovery_key column not available",
)
def test_trim_username_matches_padded_account(client):
    suffix = uuid.uuid4().hex[:8]
    username = f"Primexia_{suffix}"
    raw_key = "trimkey12345678"
    hashed = bcrypt.hashpw(raw_key.encode("utf-8"), bcrypt.gensalt(4)).decode("utf-8")

    with get_db_cursor() as db:
        db.execute(
            (
                "INSERT INTO users (username, email, hash, date, auth_type, recovery_key) "
                "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id"
            ),
            (f"  {username}  ", f"{username}@example.invalid", "x", "1970-01-01", "normal", hashed),
        )

    resp = client.post(
        "/reset_password_recovery_key",
        data={"username": username, "recovery_key": raw_key},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)
    assert "/discord_reset_password_page" in resp.headers.get("Location", "")


@pytest.mark.skipif(
    not _recovery_key_column_available(),
    reason="recovery_key column not available",
)
def test_generate_recovery_key_after_login(client):
    user_id, username, _, _ = _create_user()
    password = "RecoveryKeyPass1!"
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(4)).decode("utf-8")
    with get_db_cursor() as db:
        db.execute("UPDATE users SET hash=%s WHERE id=%s", (hashed, user_id))

    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    resp = client.post(
        "/generate_recovery_key",
        data={"password": password},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Backup Recovery Key is:" in resp.data

    with get_db_cursor() as db:
        db.execute("SELECT recovery_key FROM users WHERE id=%s", (user_id,))
        row = db.fetchone()
        assert row is not None
        assert row[0] is not None
