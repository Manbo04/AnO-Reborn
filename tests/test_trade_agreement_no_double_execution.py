"""Regression test for a real double-execution/double-spend bug found live
2026-09-23 while auditing app_core/trade_agreements/ during the account
cross-contamination investigation (unrelated to that bug, found along the
way -- see app_core/trade_agreements/repositories.py's lock_active_agreement()
docstring for the full mechanism).

activate_agreement() sets next_execution=now() in its own transaction, then
the accept route calls execute_trade_agreement() a moment later in a
SEPARATE transaction. In that window the agreement is genuinely 'active'
with next_execution<=now() -- visible to a concurrent scheduled tick, which
could independently execute the same agreement a second time. The FOR
UPDATE lock serialized the two callers but didn't stop the second one from
blindly re-executing once granted the lock.

This test directly proves the fix using the real local database (not a
mocked cursor -- a WHERE-clause correctness fix needs real SQL evaluation
to mean anything): lock the agreement once (simulating the first,
legitimate execution, which pushes next_execution into the future the same
way complete_or_reschedule_agreement does), then attempt to lock it again
(simulating a second, racing caller) and assert it finds no row.
"""
import uuid

import bcrypt
import pytest

from database import get_db_connection
from app_core.trade_agreements.repositories import (
    activate_agreement,
    lock_active_agreement,
    complete_or_reschedule_agreement,
)

pytestmark = pytest.mark.no_server

TEST_PASSWORD = bcrypt.hashpw(b"correct-horse-battery", bcrypt.gensalt()).decode()


def _create_user(db, suffix):
    username = f"dbltest_{suffix}_{uuid.uuid4().hex[:8]}"
    db.execute(
        """
        INSERT INTO users (username, email, date, hash, auth_type)
        VALUES (%s, %s, '2026-09-23', %s, 'normal')
        RETURNING id
        """,
        (username, f"{username}@example.com", TEST_PASSWORD),
    )
    return db.fetchone()[0]


def _create_agreement(db, proposer_id, receiver_id):
    db.execute(
        """
        INSERT INTO trade_agreements
            (proposer_id, proposer_resource, proposer_amount,
             receiver_id, receiver_resource, receiver_amount,
             interval_hours, max_executions, execution_count, status)
        VALUES (%s, 'gold', 10, %s, 'gold', 10, 24, NULL, 0, 'pending')
        RETURNING id
        """,
        (proposer_id, receiver_id),
    )
    return db.fetchone()[0]


def test_second_lock_after_execution_finds_no_row():
    """The core fix: after one caller executes and reschedules, a second
    (racing) caller's lock_active_agreement() must find nothing to execute,
    not the same row again."""
    with get_db_connection() as conn:
        db = conn.cursor()
        proposer_id = _create_user(db, "proposer")
        receiver_id = _create_user(db, "receiver")
        agreement_id = _create_agreement(db, proposer_id, receiver_id)

        activate_agreement(db, agreement_id)
        conn.commit()

        try:
            # First caller: locks it, "executes" it, reschedules -- mirrors
            # what execute_trade_agreement() does after a successful transfer.
            first = lock_active_agreement(db, agreement_id)
            assert first is not None, "first caller must find the just-activated agreement"

            from datetime import datetime, timedelta

            complete_or_reschedule_agreement(
                db, agreement_id, new_execution_count=1,
                next_execution=datetime.utcnow() + timedelta(hours=24),
                completed=False,
            )
            conn.commit()

            # Second (racing) caller: must NOT find this agreement due again.
            second = lock_active_agreement(db, agreement_id)
            assert second is None, (
                "a second concurrent caller found the SAME agreement still "
                "due -- this is the double-execution bug, it must return "
                "None once next_execution has been pushed into the future"
            )
        finally:
            db.execute("DELETE FROM trade_agreements WHERE id = %s", (agreement_id,))
            db.execute("DELETE FROM users WHERE id IN (%s, %s)", (proposer_id, receiver_id))
            conn.commit()


def test_freshly_activated_agreement_is_still_lockable():
    """Sanity check the fix isn't overly strict: a just-activated agreement
    (next_execution=now(), never executed) must still be found -- this is
    the legitimate "execute immediately on accept" path."""
    with get_db_connection() as conn:
        db = conn.cursor()
        proposer_id = _create_user(db, "proposer2")
        receiver_id = _create_user(db, "receiver2")
        agreement_id = _create_agreement(db, proposer_id, receiver_id)

        activate_agreement(db, agreement_id)
        conn.commit()

        try:
            row = lock_active_agreement(db, agreement_id)
            assert row is not None, "a freshly-activated agreement must still be lockable"
            assert row[0] == agreement_id
        finally:
            conn.rollback()
            db.execute("DELETE FROM trade_agreements WHERE id = %s", (agreement_id,))
            db.execute("DELETE FROM users WHERE id IN (%s, %s)", (proposer_id, receiver_id))
            conn.commit()
