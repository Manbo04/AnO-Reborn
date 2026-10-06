"""Sign up -> delete own account (with password) -> account is gone and the
credentials no longer log in. Replaces the legacy test_~deletion.py /
test_repro_delete_signup.py HTTP tests, whose "logged in" check was just
"some cookie exists" (always true now).
"""
import uuid

import pytest

from database import get_db_connection
from tests._db_cleanup import purge_users_where

PASSWORD = "testpassword123"


@pytest.mark.no_server
def test_signup_delete_then_login_fails_and_name_is_reusable(monkeypatch):
    import signup as signup_module
    from app import app

    monkeypatch.setattr(signup_module, "verify_recaptcha", lambda resp: True)
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False

    name = f"del_{uuid.uuid4().hex[:8]}"
    form = {
        "username": name,
        "email": f"{name}@example.com",
        "password": PASSWORD,
        "confirmation": PASSWORD,
        "key": "testkey12345",
        "continent": "1",
        "terms_agree": "on",
    }
    try:
        with app.test_client() as client:
            r = client.post("/signup", data=form)
            assert r.status_code in (302, 303), r.status_code
            with client.session_transaction() as sess:
                assert sess.get("user_id")

            r = client.post("/delete_own_account", data={"confirm_password": PASSWORD})
            assert r.status_code in (302, 303)
            with client.session_transaction() as sess:
                assert not sess.get("user_id")

        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute("SELECT 1 FROM users WHERE username = %s", (name,))
            assert db.fetchone() is None

        with app.test_client() as client:
            client.post("/login/", data={"username": name, "password": PASSWORD})
            with client.session_transaction() as sess:
                assert not sess.get("user_id")

            # The same name/email can sign up again (no leftover blocker).
            r = client.post("/signup", data=form)
            assert r.status_code in (302, 303), r.status_code
    finally:
        with get_db_connection() as conn:
            db = conn.cursor()
            purge_users_where(db, "username = %s", (name,))
            conn.commit()
