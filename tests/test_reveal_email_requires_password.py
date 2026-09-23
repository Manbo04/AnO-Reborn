"""Regression test for a hardening gap closed 2026-09-23 at Dede's explicit
request, in the same family as delete_own_account()/reset_account()/
twofa_disable() (see [[ano-account-cross-contamination-recurrence-2026-09-22]]):
those all require the account's current password before a destructive
action, not just a valid session, per the 2026-09-05 incident where a
stolen session cookie alone was enough to act as the account. The /account
page previously rendered mask_email(user.email) to anyone with a valid
session -- readable PII behind session auth alone. Dede asked for this to
require a fresh password too, same as delete/reset.

Fixed: GET /account no longer renders any form of the real email in its
HTML. A new POST /account/reveal_email requires the correct current
password (bcrypt-checked against the real hash, same pattern as the other
step-up routes) and returns the email as JSON only on success.
"""
import uuid

import bcrypt
import pytest

from database import get_db_connection

REAL_PASSWORD = "correct-horse-battery-staple-2026"
PASSWORD_HASH = bcrypt.hashpw(REAL_PASSWORD.encode(), bcrypt.gensalt()).decode()


@pytest.fixture
def emailed_user():
    with get_db_connection() as conn:
        db = conn.cursor()
        username = f"revemail_{uuid.uuid4().hex[:8]}"
        # Deliberately unrelated to `username` -- the account page legitimately
        # renders the username elsewhere, so reusing it here would make the
        # leak-detection assertion pass for the wrong reason.
        email = f"secretmail-{uuid.uuid4().hex[:12]}@example.com"
        db.execute(
            """
            INSERT INTO users (username, email, date, hash, auth_type)
            VALUES (%s, %s, '2026-09-23', %s, 'normal')
            RETURNING id
            """,
            (username, email, PASSWORD_HASH),
        )
        user_id = db.fetchone()[0]
        db.execute(
            "INSERT INTO stats (id, location, gold) VALUES (%s, 'Tundra', 0)",
            (user_id,),
        )
        conn.commit()

    yield user_id, email

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("DELETE FROM stats WHERE id = %s", (user_id,))
        db.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()


def test_account_page_never_renders_the_real_email(client, emailed_user):
    user_id, email = emailed_user
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    resp = client.get("/account")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert email not in body, "the real email leaked into the account page HTML"
    local_part = email.split("@")[0]
    assert local_part not in body, "the email's local part leaked into the page (e.g. via a mask)"


def test_reveal_email_without_password_is_rejected(client, emailed_user):
    """Stands in for an attacker with only a stolen/leaked session cookie
    (the CSRF-disabled test client, same as the delete/reset tests)."""
    user_id, email = emailed_user
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    resp = client.post("/account/reveal_email", data={})

    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_reveal_email_with_wrong_password_is_rejected(client, emailed_user):
    user_id, email = emailed_user
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    resp = client.post(
        "/account/reveal_email", data={"confirm_password": "definitely-wrong"}
    )

    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_reveal_email_with_correct_password_succeeds(client, emailed_user):
    user_id, email = emailed_user
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    resp = client.post(
        "/account/reveal_email", data={"confirm_password": REAL_PASSWORD}
    )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["email"] == email
