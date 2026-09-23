"""Regression test for a real double-grant race found live 2026-09-23
while auditing app_core/tutorial/ during the account cross-contamination
investigation (unrelated to that bug, found along the way).

claim_tutorial_reward() (the direct /api/tutorial/claim endpoint) and
advance_tutorial_step_by_action() (called as a side effect of building
purchases) both read tutorial_chapters_claimed/tutorial_graduated_at,
checked membership in Python, then wrote back an unconditional UPDATE
with no lock and no atomic guard -- two concurrent claims for the same
chapter (or two concurrent graduation claims) both read "not yet
claimed" before either commits, both pass the check, and both grant real
gold/resources for a single milestone.

Fixed with an atomic conditional UPDATE (PostgreSQL's array containment
operator for the chapter array, a plain NULL check for the graduation
timestamp) so the idempotency check IS the write -- correct regardless
of locking, no advisory lock needed.

Uses real concurrency (two threads, each with its own real Flask request
context, a barrier forcing overlap) against the real local ano_staging
database, calling the real claim_tutorial_reward() function directly --
same style as this session's other race fixes.
"""
import threading
import uuid

import bcrypt
import pytest

from database import get_db_connection

TEST_PASSWORD = bcrypt.hashpw(b"correct-horse-battery", bcrypt.gensalt()).decode()


@pytest.fixture
def fresh_user():
    with get_db_connection() as conn:
        db = conn.cursor()
        username = f"tutclaim_{uuid.uuid4().hex[:8]}"
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


def _race_claim_requests(app, user_id, payload):
    barrier = threading.Barrier(2)
    errors = []

    def _run(slot):
        try:
            with app.test_request_context(
                "/api/tutorial/claim", method="POST", json=payload
            ):
                from flask import session
                from app_core.tutorial.routes import claim_tutorial_reward

                session["user_id"] = user_id
                barrier.wait(timeout=5)
                claim_tutorial_reward()
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=_run, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    return errors


def test_two_concurrent_chapter_claims_grant_only_once(fresh_user):
    from app import app
    from app_core.tutorial.rewards import CHAPTER_REWARDS

    chapter_idx = 3
    expected_money = CHAPTER_REWARDS.get(chapter_idx, {}).get("money", 0)
    assert expected_money > 0, "chapter 3 must have a money reward for this test to mean anything"

    errors = _race_claim_requests(app, fresh_user, {"chapter_index": chapter_idx})
    assert not errors, f"racer thread(s) raised: {errors}"

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT gold, tutorial_chapters_claimed FROM stats WHERE id = %s", (fresh_user,))
        gold, claimed = db.fetchone()

    assert gold == expected_money, (
        f"gold is {gold}, expected exactly {expected_money} (one chapter claim) -- "
        f"a higher value means the same chapter reward was granted twice"
    )
    assert list(claimed) == [chapter_idx], f"expected claimed=[{chapter_idx}], got {claimed}"


def test_two_concurrent_graduation_claims_grant_only_once(fresh_user):
    from app import app
    from app_core.tutorial.rewards import GRADUATION_REWARD

    expected_money = GRADUATION_REWARD.get("money", 0)
    assert expected_money > 0, "graduation must have a money reward for this test to mean anything"

    errors = _race_claim_requests(app, fresh_user, {"graduate": True})
    assert not errors, f"racer thread(s) raised: {errors}"

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT gold, tutorial_graduated_at FROM stats WHERE id = %s", (fresh_user,))
        gold, graduated_at = db.fetchone()

    assert gold == expected_money, (
        f"gold is {gold}, expected exactly {expected_money} (one graduation claim) -- "
        f"a higher value means the graduation bonus was granted twice"
    )
    assert graduated_at is not None
