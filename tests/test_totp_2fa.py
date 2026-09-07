"""Tests for real TOTP two-factor authentication (RFC 6238).

Mirrors tests/test_session_epoch.py's shape: real `client` fixture, live
Railway Postgres via get_db_cursor.

Per CLAUDE.md's Single Test Account Discipline, every case here that
touches a real account row uses id 16 ("Tester of the Game") -- never a
throwaway user. An autouse fixture unconditionally force-clears its 2FA
state (secret, enabled flag, backup codes) both BEFORE and AFTER every test
in this file, even if a test fails midway -- leaving 2FA enabled on id 16
with a secret nobody has scanned would lock every other manual/interactive
test in this repo out of that account.

Account 16's own auth_type is 'discord' (no password-login row shape), so
the password-login-path test below mocks the DB/bcrypt layer the same way
tests/test_login_post.py already does for this exact account id, rather
than depending on a real password for it. Everything that checks 2FA state
itself (has_2fa_enabled, enrollment, disable) hits the real users row for
id 16.
"""
import time
from unittest.mock import MagicMock, patch

import pyotp
import pytest

from database import get_db_cursor
from app_core.auth import totp

TEST_USER_ID = 16


def _get_row():
    with get_db_cursor() as db:
        db.execute(
            "SELECT totp_secret_encrypted, totp_enabled FROM users WHERE id=%s",
            (TEST_USER_ID,),
        )
        return db.fetchone()


def _current_epoch():
    with get_db_cursor() as db:
        db.execute("SELECT session_epoch FROM users WHERE id=%s", (TEST_USER_ID,))
        return db.fetchone()[0]


def _force_clear_2fa():
    """Directly wipe 2FA state on account 16 -- deliberately not routed
    through totp.disable_2fa() itself, so teardown still works even if
    disable_2fa is the thing under test and broken."""
    with get_db_cursor() as db:
        db.execute(
            "UPDATE users SET totp_secret_encrypted=NULL, totp_enabled=FALSE, "
            "totp_enrolled_at=NULL WHERE id=%s",
            (TEST_USER_ID,),
        )
        db.execute("DELETE FROM totp_backup_codes WHERE user_id=%s", (TEST_USER_ID,))


def _enable_2fa():
    """Enroll + confirm real 2FA on account 16, returning (secret, backup_codes)."""
    from app import app

    with app.test_request_context():
        with get_db_cursor() as db:
            secret = totp.start_or_resume_enrollment(db, TEST_USER_ID)
            code = pyotp.TOTP(secret).now()
            codes = totp.confirm_enrollment(db, TEST_USER_ID, code)
    assert codes is not None, "setup: confirm_enrollment unexpectedly failed"
    return secret, codes


@pytest.fixture(autouse=True)
def _twofa_clean_on_account_16():
    """Guarantee account 16 starts AND ends every test in this file with
    2FA disabled, regardless of pass/fail."""
    _force_clear_2fa()
    try:
        yield
    finally:
        _force_clear_2fa()


@pytest.fixture
def client():
    from app import app

    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_client() as c:
        yield c


# --- Crypto/DB ---------------------------------------------------------


def test_encrypt_decrypt_round_trip():
    from app import app

    with app.test_request_context():
        secret = pyotp.random_base32()
        encrypted = totp._encrypt_secret(secret)
        assert encrypted != secret
        assert totp._decrypt_secret(encrypted) == secret


def test_enrollment_confirm_wrong_code_stays_disabled():
    from app import app

    with app.test_request_context():
        with get_db_cursor() as db:
            totp.start_or_resume_enrollment(db, TEST_USER_ID)
            result = totp.confirm_enrollment(db, TEST_USER_ID, "000000")

    assert result is None
    row = _get_row()
    assert row[1] is False


def test_enrollment_confirm_correct_code_enables_and_returns_ten_codes():
    secret, codes = _enable_2fa()
    assert len(codes) == 10
    assert len(set(codes)) == 10
    row = _get_row()
    assert row[1] is True
    assert row[0] is not None


def test_backup_code_is_single_use():
    from app import app

    _secret, codes = _enable_2fa()
    backup_code = codes[0]

    with app.test_request_context():
        assert totp.verify_login_code(TEST_USER_ID, backup_code) is True
        assert totp.verify_login_code(TEST_USER_ID, backup_code) is False


def test_disable_wipes_secret_and_backup_codes():
    from app import app

    _enable_2fa()
    with app.test_request_context():
        with get_db_cursor() as db:
            totp.disable_2fa(db, TEST_USER_ID)

    row = _get_row()
    assert row[0] is None
    assert row[1] is False
    with get_db_cursor() as db:
        db.execute(
            "SELECT COUNT(*) FROM totp_backup_codes WHERE user_id=%s", (TEST_USER_ID,)
        )
        assert db.fetchone()[0] == 0


# --- Session-epoch integration ------------------------------------------


def test_enabling_2fa_bumps_session_epoch():
    before = _current_epoch()
    _enable_2fa()
    assert _current_epoch() == before + 1


def test_disabling_2fa_bumps_session_epoch():
    from app import app

    _enable_2fa()
    before = _current_epoch()
    with app.test_request_context():
        with get_db_cursor() as db:
            totp.disable_2fa(db, TEST_USER_ID)
    assert _current_epoch() == before + 1


# --- End-to-end login gate ------------------------------------------------


def test_password_login_with_2fa_redirects_to_login_2fa(client):
    """Account 16's own auth_type is 'discord', so this mocks the DB/bcrypt
    layer the same way test_login_post.py does for this same account id --
    the point under test is login()'s 2FA gate, not real password auth."""
    import bcrypt as bcrypt_module

    _enable_2fa()

    hashed = bcrypt_module.hashpw(b"whatever", bcrypt_module.gensalt(4))
    user_row = (TEST_USER_ID, "Tester of the Game", "t@test.invalid", "", hashed, "normal")
    mock_db = MagicMock()
    mock_db.fetchone.return_value = user_row

    with patch("login.get_request_cursor") as get_cur:
        get_cur.return_value.__enter__.return_value = mock_db
        with patch("login._detect_users_schema", return_value=(False, False)):
            with patch("login.bcrypt.checkpw", return_value=True):
                resp = client.post(
                    "/login/",
                    data={"username": "Tester of the Game", "password": "whatever"},
                    follow_redirects=False,
                    environ_overrides={"REMOTE_ADDR": "203.0.113.61"},
                )

    assert resp.status_code in (302, 303)
    assert resp.headers.get("Location", "").rstrip("/").endswith("/login/2fa")
    with client.session_transaction() as sess:
        assert sess.get("pending_2fa_user_id") == TEST_USER_ID
        assert sess.get("pending_2fa_auth_type") == "password"
        assert "user_id" not in sess


def test_discord_login_with_2fa_redirects_to_login_2fa(client):
    _enable_2fa()

    mock_db = MagicMock()
    mock_db.fetchone.return_value = (TEST_USER_ID,)

    mock_discord_resp = MagicMock()
    mock_discord_resp.status_code = 200
    mock_discord_resp.json.return_value = {"id": "999999999999"}
    mock_discord_session = MagicMock()
    mock_discord_session.get.return_value = mock_discord_resp

    with client.session_transaction() as sess:
        sess["oauth2_token"] = {"access_token": "fake"}

    with patch("login.get_request_cursor") as get_cur, patch(
        "login.make_session", return_value=mock_discord_session
    ):
        get_cur.return_value.__enter__.return_value = mock_db
        resp = client.get(
            "/discord_login/",
            follow_redirects=False,
            environ_overrides={"REMOTE_ADDR": "203.0.113.62"},
        )

    assert resp.status_code in (302, 303)
    assert resp.headers.get("Location", "").rstrip("/").endswith("/login/2fa")
    with client.session_transaction() as sess:
        assert sess.get("pending_2fa_user_id") == TEST_USER_ID
        assert sess.get("pending_2fa_auth_type") == "discord"
        assert "user_id" not in sess


def test_google_login_with_2fa_redirects_to_login_2fa(client):
    _enable_2fa()

    mock_db = MagicMock()
    mock_db.fetchone.return_value = (TEST_USER_ID,)

    mock_userinfo_resp = MagicMock()
    mock_userinfo_resp.json.return_value = {
        "sub": "google-fake-id",
        "email": "fake@example.invalid",
    }
    mock_google_session = MagicMock()
    mock_google_session.fetch_token.return_value = {"access_token": "fake"}
    mock_google_session.get.return_value = mock_userinfo_resp

    with client.session_transaction() as sess:
        sess["google_oauth2_state"] = "fakestate"

    with patch("database.get_request_cursor") as get_cur, patch(
        "app_core.auth.google_auth.make_google_session", return_value=mock_google_session
    ):
        get_cur.return_value.__enter__.return_value = mock_db
        resp = client.get(
            "/login/google/callback?state=fakestate&code=fakecode",
            follow_redirects=False,
            environ_overrides={"REMOTE_ADDR": "203.0.113.63"},
        )

    assert resp.status_code in (302, 303)
    assert resp.headers.get("Location", "").rstrip("/").endswith("/login/2fa")
    with client.session_transaction() as sess:
        assert sess.get("pending_2fa_user_id") == TEST_USER_ID
        assert sess.get("pending_2fa_auth_type") == "google"
        assert "user_id" not in sess


def test_login_2fa_wrong_code_rejected(client):
    _enable_2fa()
    with client.session_transaction() as sess:
        sess["pending_2fa_user_id"] = TEST_USER_ID
        sess["pending_2fa_auth_type"] = "password"
        sess["pending_2fa_started_at"] = time.time()

    resp = client.post(
        "/login/2fa",
        data={"code": "000000"},
        follow_redirects=False,
        environ_overrides={"REMOTE_ADDR": "203.0.113.64"},
    )

    assert resp.status_code == 400
    with client.session_transaction() as sess:
        assert "user_id" not in sess
        # Pending state survives a wrong attempt so the player can retry.
        assert sess.get("pending_2fa_user_id") == TEST_USER_ID


def test_login_2fa_correct_code_completes_login(client):
    secret, _codes = _enable_2fa()
    with client.session_transaction() as sess:
        sess["pending_2fa_user_id"] = TEST_USER_ID
        sess["pending_2fa_auth_type"] = "password"
        sess["pending_2fa_started_at"] = time.time()

    code = pyotp.TOTP(secret).now()
    resp = client.post(
        "/login/2fa",
        data={"code": code},
        follow_redirects=False,
        environ_overrides={"REMOTE_ADDR": "203.0.113.65"},
    )

    assert resp.status_code in (302, 303)
    with client.session_transaction() as sess:
        assert sess.get("user_id") == TEST_USER_ID
        assert "pending_2fa_user_id" not in sess


def test_login_2fa_backup_code_completes_login_and_is_consumed(client):
    _secret, codes = _enable_2fa()
    backup_code = codes[0]
    with client.session_transaction() as sess:
        sess["pending_2fa_user_id"] = TEST_USER_ID
        sess["pending_2fa_auth_type"] = "password"
        sess["pending_2fa_started_at"] = time.time()

    resp = client.post(
        "/login/2fa",
        data={"code": backup_code},
        follow_redirects=False,
        environ_overrides={"REMOTE_ADDR": "203.0.113.66"},
    )

    assert resp.status_code in (302, 303)
    with client.session_transaction() as sess:
        assert sess.get("user_id") == TEST_USER_ID

    from app import app

    with app.test_request_context():
        assert totp.verify_login_code(TEST_USER_ID, backup_code) is False


def test_login_2fa_pending_state_expires_after_ttl(client):
    with client.session_transaction() as sess:
        sess["pending_2fa_user_id"] = TEST_USER_ID
        sess["pending_2fa_auth_type"] = "password"
        sess["pending_2fa_started_at"] = time.time() - 700  # > 600s TTL

    resp = client.get(
        "/login/2fa",
        follow_redirects=False,
        environ_overrides={"REMOTE_ADDR": "203.0.113.67"},
    )

    assert resp.status_code in (302, 303)
    assert resp.headers.get("Location", "").rstrip("/").endswith("/login")
    with client.session_transaction() as sess:
        assert "pending_2fa_user_id" not in sess


def test_login_2fa_is_rate_limited(client):
    remote_addr = "203.0.113.99"
    last_status = None
    for _ in range(60):
        resp = client.get("/login/2fa", environ_overrides={"REMOTE_ADDR": remote_addr})
        last_status = resp.status_code
        if last_status == 429:
            break
    assert last_status == 429, "expected /login/2fa to 429 once past the rate limit"


# --- Disable step-up (password re-confirmation) ---------------------------


def test_disable_2fa_missing_password_rejected(client):
    with client.session_transaction() as sess:
        sess["user_id"] = TEST_USER_ID
        sess["session_epoch"] = _current_epoch()

    resp = client.post(
        "/account/2fa/disable",
        data={},
        environ_overrides={"REMOTE_ADDR": "203.0.113.68"},
    )
    assert resp.status_code == 400


def test_disable_2fa_wrong_password_rejected(client):
    _enable_2fa()
    with client.session_transaction() as sess:
        sess["user_id"] = TEST_USER_ID
        sess["session_epoch"] = _current_epoch()

    with patch("bcrypt.checkpw", return_value=False):
        resp = client.post(
            "/account/2fa/disable",
            data={"confirm_password": "wrong"},
            environ_overrides={"REMOTE_ADDR": "203.0.113.69"},
        )

    assert resp.status_code == 400
    row = _get_row()
    assert row[1] is True


def test_disable_2fa_correct_password_disables(client):
    _enable_2fa()
    with client.session_transaction() as sess:
        sess["user_id"] = TEST_USER_ID
        sess["session_epoch"] = _current_epoch()

    with patch("bcrypt.checkpw", return_value=True):
        resp = client.post(
            "/account/2fa/disable",
            data={"confirm_password": "correct"},
            follow_redirects=False,
            environ_overrides={"REMOTE_ADDR": "203.0.113.70"},
        )

    assert resp.status_code in (302, 303)
    row = _get_row()
    assert row[0] is None
    assert row[1] is False
