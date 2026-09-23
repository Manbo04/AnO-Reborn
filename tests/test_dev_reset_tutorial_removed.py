"""Regression test for an unlimited-resources exploit found 2026-09-23
during the admin-panel security re-audit (account cross-contamination
investigation follow-up).

/dev/reset_tutorial was a leftover developer route: @login_required only,
no admin check, plain GET. It reset the CALLER's tutorial_chapters_claimed
to '{}' and tutorial_graduated_at to NULL. /api/tutorial/claim has no
per-chapter precondition beyond "not already in tutorial_chapters_claimed"
/ "tutorial_graduated_at IS NULL", so any player could loop:

    claim chapters 0-8 + graduate  (~17M gold + lumber/coal/rations/...)
    GET /dev/reset_tutorial
    claim everything again         -> repeat forever

i.e. unbounded gold/resource spawning for any non-admin account -- the
exact capability the admin command center's add-resource is supposed to
be the only (super-admin-gated) path to. Also CSRF-able (GET) and leaked
full tracebacks on error. Removed outright: nothing links to it, and the
tutorial_step column it "migrated" is covered by migration 0075.

Runs against the real local ano_staging database.
"""
import uuid

import bcrypt
import pytest

from database import get_db_connection

TEST_PASSWORD = bcrypt.hashpw(b"correct-horse-battery", bcrypt.gensalt()).decode()


@pytest.fixture
def fresh_user():
    with get_db_connection() as conn:
        db = conn.cursor()
        username = f"devreset_{uuid.uuid4().hex[:8]}"
        db.execute(
            """
            INSERT INTO users (username, email, date, hash, auth_type)
            VALUES (%s, %s, '2026-09-23', %s, 'normal')
            RETURNING id
            """,
            (username, f"{username}@example.com", TEST_PASSWORD),
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
        db.execute("DELETE FROM user_economy WHERE user_id = %s", (user_id,))
        db.execute("DELETE FROM stats WHERE id = %s", (user_id,))
        db.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()


def _claim_graduation(app, user_id):
    with app.test_request_context(
        "/api/tutorial/claim", method="POST", json={"graduate": True}
    ):
        from flask import session
        from app_core.tutorial.routes import claim_tutorial_reward

        session["user_id"] = user_id
        claim_tutorial_reward()


def _gold(user_id):
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT gold FROM stats WHERE id = %s", (user_id,))
        return db.fetchone()[0]


def test_player_cannot_reset_tutorial_to_reclaim_rewards(fresh_user):
    from app import app
    from app_core.tutorial.rewards import GRADUATION_REWARD

    expected = GRADUATION_REWARD["money"]

    _claim_graduation(app, fresh_user)
    assert _gold(fresh_user) == expected

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = fresh_user
    resp = client.get("/dev/reset_tutorial")
    assert resp.status_code == 404, (
        f"/dev/reset_tutorial answered {resp.status_code} for a regular player"
    )

    _claim_graduation(app, fresh_user)
    assert _gold(fresh_user) == expected, (
        f"gold is {_gold(fresh_user)}, expected {expected} -- the graduation "
        f"bonus was granted twice after a player-triggered tutorial reset"
    )
