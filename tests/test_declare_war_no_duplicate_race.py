"""Regression test for a real duplicate-war race found live 2026-09-23
while auditing wars/routes.py during the account cross-contamination
investigation (unrelated to that bug, found along the way).

declare_war() checks "not already at war with this nation" via a plain
SELECT before INSERTing a new `wars` row. Unlike establish_coalition's
similar SELECT-then-INSERT check (protected by a real DB UNIQUE
constraint on colNames.name / coalitions_legacy.userid), `wars` has no
constraint on (attacker, defender) at all -- two concurrent declare_war
calls for the same pair could both pass the check before either commits,
creating two simultaneous active war rows between the same two nations.
That doubles the attacker's total supply/morale pool for the ground-war
flow, and a peace offer accepted on one row would leave the other
silently still active. Fixed by adding a pg_advisory_xact_lock keyed on
both nation ids (LEAST/GREATEST, order-independent).

Uses real concurrency (two threads, each with its own real Flask request
context, a barrier forcing overlap) against the real local ano_staging
database, calling the real unmodified declare_war() function directly --
same style as this session's other wars/coalitions race fixes.
"""
import threading
import uuid

import bcrypt
import pytest

from database import get_db_connection

TEST_PASSWORD = bcrypt.hashpw(b"correct-horse-battery", bcrypt.gensalt()).decode()


def _create_user_with_provinces(db, suffix, province_count):
    username = f"declarewar_{suffix}_{uuid.uuid4().hex[:8]}"
    db.execute(
        """
        INSERT INTO users (username, email, date, hash, auth_type)
        VALUES (%s, %s, '2026-09-23', %s, 'normal')
        RETURNING id
        """,
        (username, f"{username}@example.com", TEST_PASSWORD),
    )
    user_id = db.fetchone()[0]
    for i in range(province_count):
        db.execute(
            "INSERT INTO provinces (userId, provinceName) VALUES (%s, %s)",
            (user_id, f"Province {i}"),
        )
    return user_id


@pytest.fixture
def matched_pair():
    """Two nations with equal province counts -- comfortably inside
    declare_war's +3/-1 province-count eligibility window."""
    with get_db_connection() as conn:
        db = conn.cursor()
        attacker_id = _create_user_with_provinces(db, "attacker", 5)
        defender_id = _create_user_with_provinces(db, "defender", 5)
        conn.commit()

    yield {"attacker_id": attacker_id, "defender_id": defender_id}

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            "DELETE FROM wars WHERE (attacker=%s AND defender=%s) OR (attacker=%s AND defender=%s)",
            (attacker_id, defender_id, defender_id, attacker_id),
        )
        db.execute("DELETE FROM provinces WHERE userId IN (%s, %s)", (attacker_id, defender_id))
        db.execute("DELETE FROM users WHERE id IN (%s, %s)", (attacker_id, defender_id))
        conn.commit()


def test_two_concurrent_declarations_create_only_one_war(matched_pair):
    from app import app
    from wars.routes import declare_war

    attacker_id = matched_pair["attacker_id"]
    defender_id = matched_pair["defender_id"]

    barrier = threading.Barrier(2)
    errors = []

    def _run(slot):
        try:
            with app.test_request_context(
                "/declare_war",
                method="POST",
                data={
                    "defender": str(defender_id),
                    "description": "test war",
                    "warType": "Raze",
                },
            ):
                from flask import session

                session["user_id"] = attacker_id
                barrier.wait(timeout=5)
                declare_war()
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=_run, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors, f"racer thread(s) raised: {errors}"

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            """
            SELECT COUNT(*) FROM wars
            WHERE ((attacker=%s AND defender=%s) OR (attacker=%s AND defender=%s))
              AND peace_date IS NULL
            """,
            (attacker_id, defender_id, defender_id, attacker_id),
        )
        active_war_count = db.fetchone()[0]

    assert active_war_count == 1, (
        f"found {active_war_count} simultaneous active wars between the "
        f"same pair after two concurrent declare_war calls, expected "
        f"exactly 1 -- this is the duplicate-war race"
    )
