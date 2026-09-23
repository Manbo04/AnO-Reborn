"""Regression test for a real race condition found live 2026-09-23 while
auditing wars/routes.py during the account cross-contamination
investigation (unrelated to that bug, found along the way).

nuclear_strike() and strategic_airstrike() read the attacker's weapon
quantity (nukes/icbms/bombers), checked it was enough, then decremented it
with a blind `UPDATE ... SET quantity = quantity - %s` -- no lock between
the read and the write. drone_strike() and cruise_missile_strike() already
had this exact pattern fixed on 2026-09-13 via a per-attacker
pg_advisory_xact_lock, but nuclear_strike/strategic_airstrike were missed.

user_military.quantity has a real DB-level CHECK (quantity >= 0)
constraint, which changes the actual failure mode from a silent double
payout into a crash: two concurrent strikes both read the same quantity,
both pass the affordability check, the first UPDATE succeeds and commits;
the second UPDATE was blocked on Postgres's own row lock and, once
unblocked, re-evaluates against the now-committed (lower) value -- driving
it negative and raising an unhandled psycopg2.errors.CheckViolation
instead of the intended graceful "not enough nukes/bombers" rejection.
That is the real, verified bug: a normal user firing the same strike
twice in quick succession (double-click, two tabs) gets an ugly unhandled
500 instead of a clean error, and depending on where in the request the
exception lands, partially-applied side effects from that request can be
left inconsistent. Fixed by adding the same pg_advisory_xact_lock
(attacker_id) already used by drone_strike/cruise_missile_strike, so the
second racer's own read correctly sees the post-first-strike quantity and
is rejected cleanly instead of crashing.

Uses real concurrency (two threads, each with its own real Flask request
context, a barrier forcing overlap) against the real local ano_staging
database, calling the real unmodified route functions directly -- same
style as this session's coalition bank double-grant fix (the full HTTP
test client doesn't reliably reproduce races here).
"""
import threading
import time
import uuid

import bcrypt
import pytest

from database import get_db_connection

TEST_PASSWORD = bcrypt.hashpw(b"correct-horse-battery", bcrypt.gensalt()).decode()


def _create_user(db, suffix):
    username = f"strike_{suffix}_{uuid.uuid4().hex[:8]}"
    db.execute(
        """
        INSERT INTO users (username, email, date, hash, auth_type)
        VALUES (%s, %s, '2026-09-23', %s, 'normal')
        RETURNING id
        """,
        (username, f"{username}@example.com", TEST_PASSWORD),
    )
    return db.fetchone()[0]


def _give_units(db, user_id, unit_name, quantity):
    db.execute(
        """
        INSERT INTO user_military (user_id, unit_id, quantity)
        SELECT %s, unit_id, %s FROM unit_dictionary WHERE name = %s
        ON CONFLICT (user_id, unit_id) DO UPDATE SET quantity = EXCLUDED.quantity
        """,
        (user_id, quantity, unit_name),
    )


def _unit_quantity(db, user_id, unit_name):
    db.execute(
        """
        SELECT um.quantity FROM user_military um
        JOIN unit_dictionary ud ON um.unit_id = ud.unit_id
        WHERE um.user_id = %s AND ud.name = %s
        """,
        (user_id, unit_name),
    )
    row = db.fetchone()
    return row[0] if row else 0


@pytest.fixture
def war_pair():
    with get_db_connection() as conn:
        db = conn.cursor()
        attacker_id = _create_user(db, "attacker")
        target_id = _create_user(db, "target")
        now = time.time()
        db.execute(
            """
            INSERT INTO wars (attacker, defender, war_type, agressor_message, start_date, last_visited)
            VALUES (%s, %s, 'ground', 'test war', %s, %s)
            RETURNING id
            """,
            (attacker_id, target_id, now, now),
        )
        war_id = db.fetchone()[0]
        db.execute(
            "INSERT INTO provinces (userId, provinceName) VALUES (%s, 'Test Province')",
            (target_id,),
        )
        conn.commit()

    yield {"attacker_id": attacker_id, "target_id": target_id, "war_id": war_id}

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("DELETE FROM wars WHERE id = %s", (war_id,))
        db.execute("DELETE FROM provinces WHERE userId = %s", (target_id,))
        db.execute("DELETE FROM user_military WHERE user_id IN (%s, %s)", (attacker_id, target_id))
        db.execute("DELETE FROM users WHERE id IN (%s, %s)", (attacker_id, target_id))
        conn.commit()


def test_nuclear_strike_single_nuke_cannot_fire_twice(war_pair):
    from app import app
    from wars.routes import nuclear_strike

    attacker_id = war_pair["attacker_id"]
    target_id = war_pair["target_id"]

    with get_db_connection() as conn:
        db = conn.cursor()
        _give_units(db, attacker_id, "nukes", 1)
        conn.commit()

    barrier = threading.Barrier(2)
    errors = []

    def _run(slot):
        try:
            with app.test_request_context(
                "/nuclear_strike",
                method="POST",
                data={"target_id": str(target_id), "weapon_type": "nuke"},
            ):
                from flask import session

                session["user_id"] = attacker_id
                barrier.wait(timeout=5)
                nuclear_strike()
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
        remaining = _unit_quantity(db, attacker_id, "nukes")

    assert remaining == 0, (
        f"attacker nuke count is {remaining} after firing twice with only 1 "
        f"in stock, expected exactly 0 -- a negative value means the strike "
        f"fired twice off a single nuke"
    )


def test_strategic_airstrike_full_loss_cannot_double_decrement(war_pair):
    """strategic_airstrike only decrements bombers actually shot down
    (lost_bombers), not the full bombers_count sent -- most of the time
    that's well below the attacker's stock, so the race doesn't hit the
    quantity>=0 floor at all. Force the exact scenario where it does: give
    the defender overwhelming fighters (with random.uniform patched out so
    the interception math is deterministic) so lost_bombers == the exact
    quantity sent, the same shape as nuclear_strike's crash -- two
    concurrent strikes both read quantity=N, both pass the check, first
    decrement succeeds (N-N=0), second blocks then re-evaluates against
    the fresh committed value and computes 0-N, violating the same
    quantity>=0 CHECK constraint that catches nuclear_strike's race.
    """
    from unittest.mock import patch

    from app import app
    from wars.routes import strategic_airstrike

    attacker_id = war_pair["attacker_id"]
    target_id = war_pair["target_id"]

    with get_db_connection() as conn:
        db = conn.cursor()
        _give_units(db, attacker_id, "bombers", 10)
        # Overwhelming fighters so every bomber sent is shot down.
        _give_units(db, target_id, "fighters", 1000)
        conn.commit()

    barrier = threading.Barrier(2)
    errors = []

    def _run(slot):
        try:
            with app.test_request_context(
                "/strategic_airstrike",
                method="POST",
                data={
                    "target_id": str(target_id),
                    "strike_target": "silo",
                    "bombers_count": "10",
                },
            ):
                from flask import session

                session["user_id"] = attacker_id
                barrier.wait(timeout=5)
                strategic_airstrike()
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=_run, args=(i,)) for i in range(2)]
    # fighter_effectiveness pinned to the top of its 0.5-1.5 range so
    # intercept_capacity (1000 * 1.5) always exceeds bombers_count=10,
    # guaranteeing lost_bombers == 10 (a full wipeout) on every call.
    with patch("random.uniform", return_value=1.5):
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

    assert not errors, f"racer thread(s) raised: {errors}"

    with get_db_connection() as conn:
        db = conn.cursor()
        remaining = _unit_quantity(db, attacker_id, "bombers")

    assert remaining == 0, (
        f"attacker bomber count is {remaining} after two concurrent "
        f"strikes each losing all 10 bombers, expected exactly 0"
    )
