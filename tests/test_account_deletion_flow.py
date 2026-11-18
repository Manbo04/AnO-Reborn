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


@pytest.mark.no_server
def test_delete_with_currency_history_works_but_active_loan_blocks(monkeypatch):
    """2026-11-18 regression: deleting a nation that had a currency
    conversion 500ed on national_currency_conversions_user_id_fkey. An
    unrepaid loan must block deletion (no walking away from debt)."""
    import signup as signup_module
    from app import app

    monkeypatch.setattr(signup_module, "verify_recaptcha", lambda resp: True)
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False

    name = f"delfk_{uuid.uuid4().hex[:8]}"
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
            assert client.post("/signup", data=form).status_code in (302, 303)
            with client.session_transaction() as sess:
                uid = sess["user_id"]
            with get_db_connection() as conn:
                db = conn.cursor()
                db.execute(
                    "INSERT INTO national_currency_conversions "
                    "(user_id, direction, gold_amount, currency_amount, rate) "
                    "VALUES (%s, \x27mint\x27, 100, 100, 1)",
                    (uid,),
                )
                db.execute(
                    "INSERT INTO user_loans (user_id, principal, balance, interest_rate, status) "
                    "VALUES (%s, 1000, 1000, 0.01, \x27active\x27)",
                    (uid,),
                )
                conn.commit()

            r = client.post("/delete_own_account", data={"confirm_password": PASSWORD})
            assert r.status_code == 400  # blocked by the active loan, not a 500
            with client.session_transaction() as sess:
                assert sess.get("user_id")

            with get_db_connection() as conn:
                db = conn.cursor()
                db.execute("UPDATE user_loans SET status=\x27repaid\x27, balance=0 WHERE user_id=%s", (uid,))
                conn.commit()

            r = client.post("/delete_own_account", data={"confirm_password": PASSWORD})
            assert r.status_code in (302, 303)
        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute("SELECT 1 FROM users WHERE username = %s", (name,))
            assert db.fetchone() is None
    finally:
        with get_db_connection() as conn:
            db = conn.cursor()
            purge_users_where(db, "username = %s", (name,))
            conn.commit()
