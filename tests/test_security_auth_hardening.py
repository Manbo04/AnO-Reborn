"""Regression tests for the 2026-10-13 security audit (auth/signup/referral/
tutorial/admin/chat/dashboard hardening). Real-DB tests use throwaway users
that are purged in teardown; nothing touches the shared test account's data
except where a test explicitly restores it.
"""
import uuid
from unittest.mock import patch

import bcrypt
import pytest
from flask import Flask

from database import get_db_connection
from tests._db_cleanup import purge_users

PW = "correct-horse-battery"
PW_HASH = bcrypt.hashpw(PW.encode(), bcrypt.gensalt(4)).decode()


def _make_user(date="2026-09-23", verified=True, referred_by=None, gold=0):
    name = f"sec_{uuid.uuid4().hex[:10]}"
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            """
            INSERT INTO users (username, email, date, hash, auth_type, is_verified,
                               referred_by_user_id)
            VALUES (%s, %s, %s, %s, 'normal', %s, %s) RETURNING id
            """,
            (name, f"{name}@example.invalid", date, PW_HASH, verified, referred_by),
        )
        uid = db.fetchone()[0]
        db.execute(
            "INSERT INTO stats (id, location, gold) VALUES (%s, 'Tundra', %s)",
            (uid, gold),
        )
        conn.commit()
    return uid, name


@pytest.fixture
def users():
    created = []

    def factory(**kw):
        uid, name = _make_user(**kw)
        created.append(uid)
        return uid, name

    yield factory
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("DELETE FROM user_economy WHERE user_id = ANY(%s)", (created,))
        db.execute("DELETE FROM login_events WHERE user_id = ANY(%s)", (created,))
        # invitees first (they reference referrers)
        purge_users(db, list(reversed(created)))
        conn.commit()


@pytest.fixture
def client():
    from app import app

    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_client() as c:
        yield c


# --- tutorial claim ---------------------------------------------------------


def test_tutorial_claim_blocked_for_new_nations(client, users):
    """New nations are paid by the server-verified Command Briefing; the
    client-trusting quiz endpoint must not pay them (was ~17M free gold)."""
    uid, _ = users(date="2026-10-13")
    with client.session_transaction() as s:
        s["user_id"] = uid
    r = client.post("/api/tutorial/claim", json={"graduate": True})
    assert r.status_code == 403
    for idx in range(9):
        assert client.post("/api/tutorial/claim", json={"chapter_index": idx}).status_code == 403
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT gold, tutorial_graduated_at FROM stats WHERE id=%s", (uid,))
        gold, grad = db.fetchone()
    assert gold == 0 and grad is None


# --- username / email validation on /register/email -------------------------


@pytest.mark.parametrize(
    "name,ok",
    [
        ("Good Nation", True),
        ("a_b-c.d'e", True),
        ("ab", False),
        ("x" * 31, False),
        ("<script>alert(1)</script>", False),
        ("  lead", False),
        ("two  spaces", False),
        ("evil\nname", False),
        ("___", False),
    ],
)
def test_validate_username(name, ok):
    from app_core.auth.email_auth import validate_username

    assert (validate_username(name) is None) is ok


def _register(client, **over):
    data = {
        "username": f"reg_{uuid.uuid4().hex[:8]}",
        "email": f"reg_{uuid.uuid4().hex[:8]}@example.invalid",
        "password": "longenough1",
        "confirmation": "longenough1",
        "continent": "1",
        "terms_agree": "1",
    }
    data.update(over)
    return client.post("/register/email", data=data)


def _user_exists(username):
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT 1 FROM users WHERE username=%s", (username,))
        return db.fetchone() is not None


def test_register_requires_captcha(client):
    name = f"cap_{uuid.uuid4().hex[:8]}"
    with patch("app_core.auth.email_auth.verify_recaptcha", return_value=False):
        r = _register(client, username=name)
    assert r.status_code == 302 and r.headers["Location"].endswith("/signup")
    assert not _user_exists(name)


@pytest.mark.parametrize(
    "over",
    [
        {"username": "<b>x</b>nation"},
        {"username": "ab"},
        {"password": "short", "confirmation": "short"},
        {"password": "x" * 80, "confirmation": "x" * 80},
        {"terms_agree": ""},
        {"email": "not-an-email"},
    ],
)
def test_register_rejects_bad_input(client, over):
    name = over.get("username") or f"bad_{uuid.uuid4().hex[:8]}"
    r = _register(client, **{**over, "username": name})
    assert r.status_code == 302 and r.headers["Location"].endswith("/signup")
    assert not _user_exists(name)


def test_register_email_duplicate_is_case_insensitive(client, users):
    uid, name = users()
    email = f"{name}@example.invalid"
    new_name = f"dup_{uuid.uuid4().hex[:8]}"
    r = _register(client, username=new_name, email=email.upper())
    assert r.status_code == 302 and r.headers["Location"].endswith("/signup")
    assert not _user_exists(new_name)
    r = _register(client, username=name.upper(), email=f"fresh_{uuid.uuid4().hex[:6]}@example.invalid")
    assert r.status_code == 302 and r.headers["Location"].endswith("/signup")


def test_signup_ip_rate_limit_counts_attempts():
    from app_core.auth import email_auth

    class FakeDb:
        def __init__(self, count):
            self.count, self.sql = count, []

        def execute(self, sql, params=None):
            self.sql.append(" ".join(sql.split()))

        def fetchone(self):
            return (self.count,)

    app = Flask(__name__)
    with app.test_request_context("/", environ_base={"REMOTE_ADDR": "198.51.100.7"}):
        assert email_auth._signup_ip_rate_limited(FakeDb(10)) is True
        db = FakeDb(0)
        assert email_auth._signup_ip_rate_limited(db) is False
        assert any(s.startswith("INSERT INTO signup_attempts") for s in db.sql)


# --- /login/email must enforce 2FA ------------------------------------------


def test_login_email_enforces_2fa(client, users):
    from database import get_db_cursor

    uid, name = users()
    email = f"{name}@example.invalid"
    with get_db_cursor() as db:
        db.execute("UPDATE users SET auth_type='email' WHERE id=%s", (uid,))
    with patch("app_core.auth.totp.has_2fa_enabled", return_value=True):
        r = client.post("/login/email", data={"email": email.upper(), "password": PW})
    assert r.status_code == 302 and r.headers["Location"].endswith("/login/2fa")
    with client.session_transaction() as s:
        assert s.get("pending_2fa_user_id") == uid
        assert "user_id" not in s


def test_login_email_without_2fa_logs_in(client, users):
    uid, name = users()
    r = client.post("/login/email", data={"email": f"{name}@example.invalid", "password": PW})
    assert r.status_code == 302
    with client.session_transaction() as s:
        assert s.get("user_id") == uid


# --- remember me --------------------------------------------------------------


def test_remember_me_unchecked_gives_session_cookie(client, users):
    uid, name = users()
    r = client.post("/login", data={"username": name, "password": PW, "remember_present": "1"})
    assert r.status_code == 302
    cookie = [h for h in r.headers.getlist("Set-Cookie") if h.startswith("session=")][-1]
    assert "expires=" not in cookie.lower()


def test_remember_me_checked_gives_persistent_cookie(client, users):
    uid, name = users()
    r = client.post(
        "/login",
        data={"username": name, "password": PW, "remember_present": "1", "rememberme": "on"},
    )
    cookie = [h for h in r.headers.getlist("Set-Cookie") if h.startswith("session=")][-1]
    assert "expires=" in cookie.lower()


# --- lockout / TOTP replay ----------------------------------------------------


def test_lockout_counter_and_clear():
    from app_core.auth import lockout

    uid = 10_000_000 + uuid.uuid4().int % 1_000_000
    assert not lockout.twofa_locked(uid)
    for _ in range(lockout.TWOFA_MAX_FAILURES):
        lockout.twofa_record_failure(uid)
    assert lockout.twofa_locked(uid)
    lockout.twofa_clear(uid)
    assert not lockout.twofa_locked(uid)


def test_login_2fa_locks_after_repeated_failures(client, users):
    import time

    from app_core.auth import lockout

    uid, _ = users()
    lockout.twofa_clear(uid)
    for i in range(lockout.TWOFA_MAX_FAILURES):
        with client.session_transaction() as s:
            s["pending_2fa_user_id"] = uid
            s["pending_2fa_auth_type"] = "password"
            s["pending_2fa_started_at"] = time.time()
        with patch("app_core.auth.totp.verify_login_code", return_value=False):
            r = client.post("/login/2fa", data={"code": "000000"})
    # the last failure ends the pending login
    assert r.status_code == 302 and r.headers["Location"].endswith("/login")
    with client.session_transaction() as s:
        assert "pending_2fa_user_id" not in s
    # even a "valid" code cannot get through the lockout
    with client.session_transaction() as s:
        s["pending_2fa_user_id"] = uid
        s["pending_2fa_started_at"] = time.time()
    with patch("app_core.auth.totp.verify_login_code", return_value=True):
        r = client.post("/login/2fa", data={"code": "123456"})
    assert r.status_code == 302
    with client.session_transaction() as s:
        assert "user_id" not in s
    lockout.twofa_clear(uid)


def test_totp_code_cannot_be_replayed(users):
    import pyotp

    from app import app
    from app_core.auth import totp
    from database import get_db_cursor

    uid, _ = users()
    with app.test_request_context():
        with get_db_cursor() as db:
            secret = totp.start_or_resume_enrollment(db, uid)
            assert totp.confirm_enrollment(db, uid, pyotp.TOTP(secret).now())
        code = pyotp.TOTP(secret).now()
        assert totp.verify_login_code(uid, code) is True
        assert totp.verify_login_code(uid, code) is False


def test_password_lockout_blocks_login(client, users):
    from app_core.auth import lockout

    uid, name = users()
    for _ in range(lockout.PASSWORD_MAX_FAILURES):
        lockout.password_record_failure(uid)
    r = client.post("/login", data={"username": name, "password": PW})
    assert r.status_code == 429
    lockout.password_clear(uid)
    r = client.post("/login", data={"username": name, "password": PW})
    assert r.status_code == 302


# --- reCAPTCHA ------------------------------------------------------------------


def test_recaptcha_fails_closed_in_prod_without_secret(monkeypatch):
    import signup

    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "production")
    monkeypatch.setenv("RECAPTCHA_SITE_KEY", "site")
    monkeypatch.delenv("RECAPTCHA_SECRET_KEY", raising=False)
    monkeypatch.setenv("SKIP_RECAPTCHA", "1")  # must be ignored in prod
    monkeypatch.setenv("CI", "1")
    assert signup.verify_recaptcha("anything") is False


def test_recaptcha_bypass_still_works_outside_prod(monkeypatch):
    import signup

    monkeypatch.delenv("RAILWAY_ENVIRONMENT_NAME", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.setenv("SKIP_RECAPTCHA", "1")
    assert signup.verify_recaptcha(None) is True


# --- password reset -----------------------------------------------------------------


def test_reset_request_keeps_valid_code_and_is_rate_limited(client, users):
    from app_core.auth import lockout  # noqa: F401

    uid, name = users()
    email = f"{name}@example.invalid"
    with patch("change.sendEmail") as send:
        client.post("/request_password_reset", data={"email": email})
        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute("SELECT url_code FROM reset_codes WHERE user_id=%s", (uid,))
            first = db.fetchone()[0]
        client.post("/request_password_reset", data={"email": email.upper()})
        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute("SELECT url_code FROM reset_codes WHERE user_id=%s", (uid,))
            second = db.fetchone()[0]
        assert first == second, "a second request must not invalidate the live code"
        for _ in range(8):
            client.post("/request_password_reset", data={"email": email})
        assert send.call_count <= 6  # capped per address
    with get_db_connection() as conn:
        conn.cursor().execute("DELETE FROM reset_codes WHERE user_id=%s", (uid,))
        conn.commit()


# --- referral -------------------------------------------------------------------------


def _gold(uid):
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT gold FROM stats WHERE id=%s", (uid,))
        return db.fetchone()[0]


def _add_days(uid, n):
    from datetime import date, timedelta

    with get_db_connection() as conn:
        db = conn.cursor()
        for i in range(n):
            db.execute(
                "INSERT INTO referral_active_days (referred_user_id, activity_date) "
                "VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (uid, date.today() - timedelta(days=i)),
            )
        conn.commit()


def test_invitee_bonus_deferred_until_verified_and_active(users):
    from app import app
    from app_core.referrals.rewards import INVITEE_SIGNUP_BONUS
    from app_core.referrals.service import grant_pending_invitee_bonus

    referrer, _ = users()
    invitee, _ = users(referred_by=referrer, verified=False)
    with app.test_request_context():
        with get_db_connection() as conn:
            db = conn.cursor()
            assert grant_pending_invitee_bonus(db, invitee) is None  # unverified
            conn.commit()
        assert _gold(invitee) == 0

        with get_db_connection() as conn:
            conn.cursor().execute("UPDATE users SET is_verified=TRUE WHERE id=%s", (invitee,))
            conn.commit()
        with get_db_connection() as conn:
            assert grant_pending_invitee_bonus(conn.cursor(), invitee) is None  # no active days
            conn.commit()
        assert _gold(invitee) == 0

        _add_days(invitee, 2)
        with get_db_connection() as conn:
            assert grant_pending_invitee_bonus(conn.cursor(), invitee)
            conn.commit()
        assert _gold(invitee) == INVITEE_SIGNUP_BONUS["money"]
        with get_db_connection() as conn:  # never paid twice
            assert grant_pending_invitee_bonus(conn.cursor(), invitee) is None
            conn.commit()
        assert _gold(invitee) == INVITEE_SIGNUP_BONUS["money"]


def test_real_activity_requires_buildings(users):
    from app_core.referrals.service import _has_real_activity

    uid, _ = users()
    with get_db_connection() as conn:
        assert _has_real_activity(conn.cursor(), uid) is False


def test_shared_network_blocks_self_referral_farming(users):
    from app_core.referrals.service import shares_network_with_referrer

    referrer, _ = users()
    sibling, _ = users(referred_by=referrer)
    ip = f"203.0.113.{uuid.uuid4().int % 250}"
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("INSERT INTO login_events (user_id, ip) VALUES (%s, %s)", (referrer, ip))
        conn.commit()
        assert shares_network_with_referrer(db, referrer, ip) is True
        assert shares_network_with_referrer(db, referrer, "198.51.100.250") is False
        assert shares_network_with_referrer(db, referrer, None) is False
    # an earlier invitee's IP also counts
    ip2 = f"203.0.114.{uuid.uuid4().int % 250}"
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("INSERT INTO login_events (user_id, ip) VALUES (%s, %s)", (sibling, ip2))
        conn.commit()
        assert shares_network_with_referrer(db, referrer, ip2) is True


def test_shared_proxy_ip_is_not_a_signal(users):
    """An IP seen across many accounts (Railway/Cloudflare hop, CGNAT) must
    never be used to reject referrals."""
    from app_core.referrals.service import SHARED_IP_MAX_ACCOUNTS, shares_network_with_referrer

    referrer, _ = users()
    crowd = [users()[0] for _ in range(SHARED_IP_MAX_ACCOUNTS + 1)]
    ip = f"203.0.115.{uuid.uuid4().int % 250}"
    with get_db_connection() as conn:
        db = conn.cursor()
        for u in [referrer] + crowd:
            db.execute("INSERT INTO login_events (user_id, ip) VALUES (%s, %s)", (u, ip))
        conn.commit()
        assert shares_network_with_referrer(db, referrer, ip) is False


# --- admin routes ----------------------------------------------------------------------


def _admin_session(client):
    # Carry the account's current session_epoch (other tests bump it) so the
    # stale-session guard in before_request does not bounce the request.
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT session_epoch FROM users WHERE id=16")
        epoch = db.fetchone()[0]
    with client.session_transaction() as s:
        s["user_id"] = 16
        s["session_epoch"] = epoch


def test_leviathan_wipe_secret_never_accepted_in_url(client):
    _admin_session(client)
    r = client.get("/admin/debug/leviathan?pass=whatever")
    assert r.status_code == 400
    # POST path with a wrong secret is rejected, not treated as a read
    r = client.post("/admin/debug/leviathan", data={"pass": "definitely-wrong"})
    assert r.status_code in (401, 403)


def test_migrate_treaties_is_post_only(client):
    _admin_session(client)
    assert client.get("/admin/migrate_treaties").status_code == 405


# --- system probes ------------------------------------------------------------------------


def test_deploy_info_public_view_is_minimal(client, monkeypatch):
    monkeypatch.setenv("ADMIN_DIAG_SECRET", "s3cret-diag")
    data = client.get("/deploy-info").get_json()
    assert set(data) <= {"git_commit", "schema_compat"}
    full = client.get("/deploy-info", headers={"X-DIAG-SECRET": "s3cret-diag"}).get_json()
    assert "boot_marker" in full and "economy_tasks" in full


def test_ready_does_not_echo_exceptions(client):
    with patch("database.schema_compat_succeeded", side_effect=RuntimeError("secret-dsn-detail")):
        r = client.get("/ready")
    assert r.status_code == 503
    assert b"secret-dsn-detail" not in r.data


# --- chat -------------------------------------------------------------------------------------


def test_chat_burst_throttle(monkeypatch):
    from app_core.chat import routes

    monkeypatch.setattr(routes, "_MIN_SECONDS_BETWEEN_MESSAGES", 0)
    uid = 20_000_000 + uuid.uuid4().int % 1_000_000
    results = [routes._throttled(uid) for _ in range(routes._BURST_MAX + 3)]
    assert results[: routes._BURST_MAX] == [False] * routes._BURST_MAX
    assert all(results[routes._BURST_MAX :])


# --- discord bot dashboard -----------------------------------------------------------------------


def test_dashboard_post_requires_csrf_and_callback_escapes():
    from discord_bot import dashboard

    dashboard.app.config["TESTING"] = True
    dashboard.app.secret_key = "t"
    c = dashboard.app.test_client()
    r = c.post("/dashboard/123/levels", data={"xp_per_message": "5"})
    assert r.status_code == 400
    with c.session_transaction() as s:
        s["csrf_token"] = "tok"
    r = c.post("/dashboard/123/levels", data={"csrf_token": "wrong"})
    assert r.status_code == 400
    r = c.get('/callback?error=<script>alert(1)</script>')
    assert b"<script>" not in r.data and r.mimetype == "text/plain"
    # a callback without the state we issued is refused
    r = c.get("/callback?code=x&state=forged")
    assert r.status_code == 400
