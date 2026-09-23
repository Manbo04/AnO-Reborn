"""Regression test for a real double-payout race found live 2026-09-23 while
auditing app_core/referrals/ during the account cross-contamination
investigation (unrelated to that bug, found along the way).

try_grant_milestones() is reached from app.py's before_request hook once a
per-SESSION 2-minute throttle (`_last_active_ping`) elapses -- not a
per-request-serialized DB throttle. A single page load fires many concurrent
requests from the same browser (confirmed via this session's own
load-testing), so multiple of them can read the same stale session
timestamp and all reach try_grant_milestones() for the same milestone at
once. The old code ran an idempotent `INSERT ... ON CONFLICT DO NOTHING`
into referral_milestone_payouts but never checked whether its OWN insert
actually won that race before calling _apply_rewards() -- every concurrent
caller paid out unconditionally, regardless of the conflict.

This test proves the fix using the real local database (not a mocked
cursor) with genuine concurrency: two threads, each on its OWN connection,
both call try_grant_milestones() for the same already-eligible milestone
with a barrier forcing them to overlap. A sequential double-call is NOT
sufficient to reproduce this bug -- the first call's INSERT commits before
the second call's earlier `already_paid` SELECT even runs, so the ordinary
happy path already blocks a purely sequential retry regardless of whether
the fix is present. Only real transaction overlap exercises the actual
race window the fix closes.
"""
import threading
import uuid

import bcrypt
import pytest

from database import get_db_connection
from app_core.referrals.service import try_grant_milestones, record_active_day

pytestmark = pytest.mark.no_server

TEST_PASSWORD = bcrypt.hashpw(b"correct-horse-battery", bcrypt.gensalt()).decode()


def _create_user(db, suffix):
    username = f"reftest_{suffix}_{uuid.uuid4().hex[:8]}"
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
    db.execute("UPDATE users SET is_verified = TRUE WHERE id = %s", (user_id,))
    return user_id


def test_two_concurrent_calls_pay_milestone_only_once():
    """The core fix: two genuinely concurrent calls to try_grant_milestones()
    for the same newly-eligible milestone, from separate connections/
    transactions with a barrier forcing overlap, must only pay out once."""
    with get_db_connection() as setup_conn:
        setup_db = setup_conn.cursor()
        referrer_id = _create_user(setup_db, "referrer")
        referred_id = _create_user(setup_db, "referred")
        setup_db.execute(
            "UPDATE users SET referred_by_user_id = %s WHERE id = %s",
            (referrer_id, referred_id),
        )
        # Pre-record today's activity on the setup connection and commit,
        # so both racing threads see the 1-day milestone as already
        # eligible (active_days >= 1) the moment they start -- isolating
        # the race to the payout INSERT itself, not the activity tracking.
        record_active_day(setup_db, referred_id)
        setup_conn.commit()

    barrier = threading.Barrier(2)
    results: list[list] = [None, None]  # type: ignore[list-item]
    errors: list[Exception] = []

    def _racer(slot):
        try:
            with get_db_connection() as conn:
                db = conn.cursor()
                barrier.wait(timeout=5)
                payouts = try_grant_milestones(db, referred_id)
                conn.commit()
                results[slot] = payouts
        except Exception as exc:  # pragma: no cover - surfaced via errors list
            errors.append(exc)

    threads = [threading.Thread(target=_racer, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    with get_db_connection() as conn:
        db = conn.cursor()
        try:
            assert not errors, f"racer thread(s) raised: {errors}"
            paid_counts = [len(r or []) for r in results]
            assert sorted(paid_counts) == [0, 1], (
                f"exactly one of the two concurrent callers should pay the "
                f"1-day milestone and the other should find it already "
                f"claimed, got payout counts {paid_counts} -- both paying "
                f"is the double-payout bug"
            )

            db.execute("SELECT gold FROM stats WHERE id = %s", (referrer_id,))
            gold = db.fetchone()[0]
            assert gold == 2_000_000, (
                f"referrer gold is {gold}, expected exactly one milestone payout "
                "(2,000,000) -- a higher value means the reward was granted twice"
            )

            db.execute(
                "SELECT COUNT(*) FROM referral_milestone_payouts "
                "WHERE referrer_user_id = %s AND referred_user_id = %s AND milestone_days = 1",
                (referrer_id, referred_id),
            )
            assert db.fetchone()[0] == 1
        finally:
            db.execute(
                "DELETE FROM referral_milestone_payouts WHERE referrer_user_id = %s OR referred_user_id = %s",
                (referrer_id, referred_id),
            )
            db.execute(
                "DELETE FROM referral_active_days WHERE referred_user_id = %s",
                (referred_id,),
            )
            db.execute("DELETE FROM user_economy WHERE user_id IN (%s, %s)", (referrer_id, referred_id))
            db.execute("DELETE FROM stats WHERE id IN (%s, %s)", (referrer_id, referred_id))
            db.execute("DELETE FROM users WHERE id IN (%s, %s)", (referrer_id, referred_id))
            conn.commit()
