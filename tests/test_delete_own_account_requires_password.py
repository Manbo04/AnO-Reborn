"""Regression test for a real bug found live 2026-09-23 while auditing
countries.py during the account cross-contamination investigation
(unrelated to that bug, but directly in its blast radius).

delete_own_account() permanently deletes the users row itself (strictly
more destructive than reset_account right above it in the same file, which
only resets game progress) yet had NONE of that route's protection.
reset_account was hardened after a real 2026-09-05 incident where a stolen
session cookie alone was enough to trigger destructive actions with a
single POST -- it now requires the account's current password.
delete_own_account still only checked login_required. The "type your
username to confirm" step in the UI is client-side JavaScript only, never
re-checked server-side, so it provided zero real protection against an
attacker who already holds a valid session cookie (a leaked/stolen cookie,
or notably the exact class of bug this session's cache_response fix
closed) and could just POST directly, bypassing the modal entirely.

Fixed by requiring the account's current password, same as reset_account.
"""
import uuid

import bcrypt
import pytest

from database import get_db_connection

REAL_PASSWORD = "correct-horse-battery-staple-2026"
PASSWORD_HASH = bcrypt.hashpw(REAL_PASSWORD.encode(), bcrypt.gensalt()).decode()


@pytest.fixture
def deletable_user():
    with get_db_connection() as conn:
        db = conn.cursor()
        username = f"delacct_{uuid.uuid4().hex[:8]}"
        db.execute(
            """
            INSERT INTO users (username, email, date, hash, auth_type)
            VALUES (%s, %s, '2026-09-23', %s, 'normal')
            RETURNING id
            """,
            (username, f"{username}@example.com", PASSWORD_HASH),
        )
        user_id = db.fetchone()[0]
        db.execute(
            "INSERT INTO stats (id, location, gold) VALUES (%s, 'Tundra', 0)",
            (user_id,),
        )
        conn.commit()

    yield user_id

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("DELETE FROM stats WHERE id = %s", (user_id,))
        db.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()


def _user_exists(user_id):
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT 1 FROM users WHERE id = %s", (user_id,))
        return db.fetchone() is not None


def test_delete_without_password_is_rejected_and_account_survives(client, deletable_user):
    """The exact attack this closes: a request carrying only a valid
    session (the CSRF-disabled test client stands in for "attacker already
    has a valid cookie") and no password must not delete the account."""
    with client.session_transaction() as sess:
        sess["user_id"] = deletable_user

    resp = client.post("/delete_own_account", data={})

    assert resp.status_code == 400, (
        f"expected a 400 rejection with no password, got {resp.status_code}"
    )
    assert _user_exists(deletable_user), (
        "account was deleted despite no password being provided -- this is "
        "the vulnerability"
    )


def test_delete_with_wrong_password_is_rejected_and_account_survives(client, deletable_user):
    with client.session_transaction() as sess:
        sess["user_id"] = deletable_user

    resp = client.post("/delete_own_account", data={"confirm_password": "definitely-wrong"})

    assert resp.status_code == 400
    assert _user_exists(deletable_user), (
        "account was deleted despite an incorrect password"
    )


def test_delete_with_correct_password_succeeds(client, deletable_user):
    with client.session_transaction() as sess:
        sess["user_id"] = deletable_user

    resp = client.post(
        "/delete_own_account",
        data={"confirm_password": REAL_PASSWORD},
        follow_redirects=False,
    )

    assert resp.status_code in (302, 200)
    assert not _user_exists(deletable_user), (
        "account should be deleted once the correct password is provided"
    )
