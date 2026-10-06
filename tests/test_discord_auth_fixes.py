"""Tests for Discord OAuth registration, login, and account management fixes."""
from tests._session import mark_validated
from unittest.mock import MagicMock, patch
import pytest

pytestmark = pytest.mark.no_server


def test_generate_discord_link_code_bypasses_password_for_discord_auth(client):
    """Discord auth accounts do not have bcrypt passwords, so generating a bot
    link code must not require or check passwords against snowflake hashes."""
    with client.session_transaction() as sess:
        sess["user_id"] = 42
        mark_validated(sess)

    dummy_db = MagicMock()
    # SELECT hash, auth_type FROM users WHERE id=%s
    dummy_db.fetchone.return_value = ("123456789012345678", "discord")

    cm = MagicMock()
    cm.__enter__.return_value = dummy_db
    cm.__exit__.return_value = False

    with patch("database.discord_link_codes_table_exists", return_value=True), \
         patch("change.users_table_has_column", return_value=True), \
         patch("change.get_request_cursor", return_value=cm), \
         patch("bot_api.create_discord_link_code") as mock_create:
        resp = client.post("/generate_discord_link_code", data={}, follow_redirects=False)

    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/account")
    mock_create.assert_called_once_with(42)


def test_generate_recovery_key_bypasses_password_for_discord_auth(client):
    """Discord auth accounts should be able to generate backup recovery keys
    without providing a non-existent password."""
    with client.session_transaction() as sess:
        sess["user_id"] = 42
        mark_validated(sess)

    dummy_db = MagicMock()
    dummy_db.fetchone.return_value = ("123456789012345678", "discord")

    cm = MagicMock()
    cm.__enter__.return_value = dummy_db
    cm.__exit__.return_value = False

    with patch("change.users_table_has_column", return_value=True), \
         patch("change.get_request_cursor", return_value=cm), \
         patch("change.create_recovery_key_for_user", return_value="deadbeef1234") as mock_create:
        resp = client.post("/generate_recovery_key", data={}, follow_redirects=False)

    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/account")
    mock_create.assert_called_once_with(dummy_db, 42)


def test_change_account_bypasses_password_for_discord_auth(client):
    """Discord auth accounts should be able to update email/username without password."""
    with client.session_transaction() as sess:
        sess["user_id"] = 42
        mark_validated(sess)

    dummy_db = MagicMock()
    # SELECT hash, auth_type FROM users WHERE id=%s
    dummy_db.fetchone.return_value = ("123456789012345678", "discord")

    cm = MagicMock()
    cm.__enter__.return_value = dummy_db
    cm.__exit__.return_value = False

    with patch("change.users_table_has_column", return_value=True), \
         patch("change.get_request_cursor", return_value=cm):
        resp = client.post(
            "/change",
            data={"email": "new@example.com", "name": "NewNation"},
            follow_redirects=False,
        )

    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/account")
    update_calls = [c[0][0] for c in dummy_db.execute.call_args_list if "UPDATE users" in c[0][0]]
    assert len(update_calls) > 0


def test_discord_login_backfills_discord_id_and_ensures_policies(client):
    """discord_login should backfill users.discord_id if missing and call _ensure_policies_row."""
    dummy_db = MagicMock()
    # SELECT id FROM users WHERE ... -> user_id 55
    dummy_db.fetchone.return_value = (55,)

    cm = MagicMock()
    cm.__enter__.return_value = dummy_db
    cm.__exit__.return_value = False

    class FakeDiscord:
        def get(self, url):
            res = MagicMock()
            res.status_code = 200
            res.json.return_value = {"id": "999888777", "username": "DiscordUser"}
            return res

    with client.session_transaction() as sess:
        sess["oauth2_token"] = {"access_token": "token123"}

    mock_totp = MagicMock()
    mock_totp.has_2fa_enabled.return_value = False

    with patch("login.get_request_cursor", return_value=cm), \
         patch("login.make_session", return_value=FakeDiscord()), \
         patch("login._ensure_policies_row") as mock_policies, \
         patch("database.users_table_has_column", return_value=True), \
         patch.dict("sys.modules", {"app_core.auth.totp": mock_totp}), \
         patch("login.complete_or_verify_login", return_value="OK") as mock_login:
        resp = client.get("/discord_login")

    mock_policies.assert_called_once_with(dummy_db, 55)
    # Check that update for discord_id was executed
    update_calls = [c for c in dummy_db.execute.call_args_list if "UPDATE users SET discord_id" in c[0][0]]
    assert len(update_calls) == 1
    assert update_calls[0][0][1] == ("999888777", 55)
    mock_login.assert_called_once()
