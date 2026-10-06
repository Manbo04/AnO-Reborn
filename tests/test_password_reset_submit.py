"""Password reset POST: schema-aware set_user_password and reset_codes."""
import time
import uuid
from unittest.mock import MagicMock, patch

import bcrypt
import pytest

from database import set_user_password
from tests._db_cleanup import purge_users_where


def test_set_user_password_updates_hash_and_password_columns():
    db = MagicMock()
    hashed = bcrypt.hashpw(b"secret12", bcrypt.gensalt(14)).decode("utf-8")
    with patch(
        "database.get_users_password_column_names",
        return_value={"hash", "password"},
    ):
        with patch("database.users_table_has_column", return_value=True):
            set_user_password(db, 42, hashed)

    calls = [c[0][0].strip() for c in db.execute.call_args_list]
    assert any("UPDATE users SET hash" in q for q in calls)
    assert any("UPDATE users SET password" in q for q in calls)
    assert any("auth_type = 'normal'" in q for q in calls)


def test_set_user_password_hash_only():
    db = MagicMock()
    hashed = bcrypt.hashpw(b"secret12", bcrypt.gensalt(14)).decode("utf-8")
    with patch(
        "database.get_users_password_column_names",
        return_value={"hash"},
    ):
        with patch("database.users_table_has_column", return_value=False):
            set_user_password(db, 7, hashed)

    calls = [c[0][0].strip() for c in db.execute.call_args_list]
    assert len(calls) == 1
    assert "UPDATE users SET hash" in calls[0]


@pytest.fixture
def client():
    from app import app

    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False  # CSRF itself: test_csrf_enforced_on_app.py
    with app.test_client() as c:
        yield c


def test_reset_password_post_success(client):
    """Full reset flow when DB is available (test account pattern)."""
    from database import get_db_cursor

    try:
        with get_db_cursor() as db:
            db.execute("SELECT 1 FROM reset_codes LIMIT 1")
    except Exception:
        pytest.skip("database not available")

    code = f"testreset_{uuid.uuid4().hex}"
    new_pw = f"ResetPw_{uuid.uuid4().hex[:8]}!"
    user_id = None
    try:
        with get_db_cursor() as db:
            username = f"pwsubmit_{uuid.uuid4().hex[:8]}"
            email = f"{username}@example.invalid"
            hashed = bcrypt.hashpw(b"oldpass1", bcrypt.gensalt(14)).decode("utf-8")
            db.execute(
                (
                    "INSERT INTO users (username, email, hash, date, auth_type) "
                    "VALUES (%s, %s, %s, %s, %s) RETURNING id"
                ),
                (username, email, hashed, "1970-01-01", "discord"),
            )
            user_id = db.fetchone()[0]
            db.execute(
                (
                    "INSERT INTO reset_codes (url_code, user_id, created_at) "
                    "VALUES (%s, %s, %s)"
                ),
                # epoch seconds, like _issue_reset_code; codes expire, so it must be fresh
                (code, user_id, str(int(time.time()))),
            )

        resp = client.post(
            f"/reset_password/{code}",
            data={"password": new_pw},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303), resp.data[:500]

        with get_db_cursor() as db:
            db.execute("SELECT auth_type, hash FROM users WHERE id=%s", (user_id,))
            row = db.fetchone()
            assert row is not None
            auth_type, stored_hash = row[0], row[1]
            assert auth_type == "normal"
            assert bcrypt.checkpw(new_pw.encode("utf-8"), stored_hash.encode("utf-8"))
            db.execute("SELECT 1 FROM reset_codes WHERE url_code=%s", (code,))
            assert db.fetchone() is None
    finally:
        if user_id is not None:
            with get_db_cursor() as db:
                db.execute("DELETE FROM reset_codes WHERE user_id=%s", (user_id,))
                purge_users_where(db, 'id=%s', (user_id,))
