"""Discord/Google-only accounts have no password: users.hash holds the
provider's numeric id. Step-up checks used to bcrypt-compare against it, so
these players could never delete/reset their account, and "Reset password"
on the account page crashed with a 500 ("Invalid salt").
"""
import uuid

import pytest

from app_core.auth.passwords import account_has_password, confirm_identity
from database import get_db_connection
from tests._db_cleanup import purge_users


def test_account_has_password_formats():
    assert account_has_password("$2b$12$abcdefghijklmnopqrstuv")
    assert account_has_password("pbkdf2:sha256:600000$x$y")
    assert not account_has_password("123456789012345678")  # Discord snowflake
    assert not account_has_password("")
    assert not account_has_password(None)


def test_confirm_identity_for_passwordless_uses_nation_name():
    assert confirm_identity("123456789012345678", "Iron Duchy", "iron duchy ")
    assert not confirm_identity("123456789012345678", "Iron Duchy", "wrong")
    assert not confirm_identity("123456789012345678", "Iron Duchy", "")
    # A real password hash never accepts the nation name.
    import bcrypt

    h = bcrypt.hashpw(b"secret-pass", bcrypt.gensalt(4)).decode()
    assert confirm_identity(h, "Iron Duchy", "secret-pass")
    assert not confirm_identity(h, "Iron Duchy", "Iron Duchy")


@pytest.fixture
def discord_user():
    name = f"Pwless {uuid.uuid4().hex[:6]}"
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            "INSERT INTO users (username, email, date, hash, auth_type) "
            "VALUES (%s, %s, '2026-10-06', %s, 'discord') RETURNING id",
            (name, f"{uuid.uuid4().hex[:8]}@example.invalid", "112233445566778899"),
        )
        uid = db.fetchone()[0]
        db.execute("INSERT INTO stats (id, location) VALUES (%s, 'Grassland')", (uid,))
        conn.commit()
    yield uid, name
    with get_db_connection() as conn:
        purge_users(conn.cursor(), [uid])
        conn.commit()


def _client(uid):
    from app import app

    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = uid
    return client


@pytest.mark.no_server
def test_passwordless_reset_password_request_does_not_500(discord_user):
    uid, _ = discord_user
    resp = _client(uid).post(
        "/account/request_password_reset", data={"current_password": "anything"}
    )
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/account")


@pytest.mark.no_server
def test_passwordless_reveal_email_with_nation_name(discord_user):
    uid, name = discord_user
    client = _client(uid)
    assert client.post("/account/reveal_email", data={"confirm_password": "nope"}).status_code == 400
    resp = client.post("/account/reveal_email", data={"confirm_password": name})
    assert resp.status_code == 200 and resp.get_json()["ok"] is True


@pytest.mark.no_server
def test_passwordless_account_can_delete_with_nation_name(discord_user):
    uid, name = discord_user
    client = _client(uid)
    assert client.post("/delete_own_account", data={"confirm_password": "wrong"}).status_code == 400
    assert client.post("/delete_own_account", data={}).status_code == 400
    resp = client.post("/delete_own_account", data={"confirm_password": name})
    assert resp.status_code == 302
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT 1 FROM users WHERE id=%s", (uid,))
        assert db.fetchone() is None


@pytest.mark.no_server
def test_account_page_asks_passwordless_player_for_nation_name(discord_user):
    from tests._session import mark_validated

    uid, _ = discord_user
    client = _client(uid)
    with client.session_transaction() as sess:
        mark_validated(sess)
    resp = client.get("/account")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Type your nation name again" in html
    assert "Enter current password to save details" not in html
