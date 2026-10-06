"""Signup is limited per client IP (signup.py: max 10 attempts / IP / day).

The client IP is request.remote_addr (ProxyFix resolves it from the one
trusted proxy hop in production), so this test sets REMOTE_ADDR directly.
Loopback is exempt (local dev), so it uses a public-looking address.
"""
import pytest

from database import get_db_connection

TEST_IP = "203.0.113.7"  # TEST-NET-3, never a real client
MAX_ATTEMPTS = 10  # keep in sync with signup.py's max_attempts


def _signup_data(n):
    return {
        "username": f"rl_user_{n}",
        "email": f"rl_user_{n}@example.com",
        "password": "testpassword123",
        "confirmation": "testpassword123",
        "key": "testkey12345",
        "continent": "1",
        "terms_agree": "on",
    }


@pytest.fixture
def clean_attempts():
    def _wipe():
        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute(
                "DELETE FROM signup_attempts WHERE ip_address = %s OR ip = %s",
                (TEST_IP, TEST_IP),
            )
            conn.commit()

    _wipe()
    yield
    _wipe()


@pytest.mark.no_server
def test_ip_rate_limit(clean_attempts, monkeypatch):
    import signup as signup_module
    from app import app

    monkeypatch.setattr(signup_module, "verify_recaptcha", lambda resp: True)
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False

    with get_db_connection() as conn:
        db = conn.cursor()
        for _ in range(MAX_ATTEMPTS):
            db.execute(
                "INSERT INTO signup_attempts (ip_address, ip, attempt_time, successful) "
                "VALUES (%s, %s, NOW(), FALSE)",
                (TEST_IP, TEST_IP),
            )
        conn.commit()

    with app.test_client() as client:
        r = client.post(
            "/signup",
            data=_signup_data(3),
            environ_base={"REMOTE_ADDR": TEST_IP},
        )
    assert r.status_code == 429, r.status_code
    assert b"Too many signup attempts" in r.data
