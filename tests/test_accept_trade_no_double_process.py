"""Regression test for a real double-accept race found live 2026-09-23
while auditing app_core/market/ during the account cross-contamination
investigation (unrelated to that bug, found along the way).

accept_trade() uses try_lock_trade()/unlock_trade() -- a SESSION-scoped
pg_try_advisory_lock/pg_advisory_unlock pair, not the transaction-scoped
pg_advisory_xact_lock used everywhere else in this codebase. Two real bugs
compounded here:

1. delete_trade_by_id() (the actual idempotency marker -- removing the
   trade row) used to run AFTER the `finally: unlock_trade(...)` block,
   so the lock was released while the trade row still existed.
2. get_trade_by_id() was a plain SELECT (no FOR UPDATE). Since a
   pg_advisory_unlock takes effect immediately, independent of the
   surrounding transaction's commit, a second concurrent accept_trade
   call could acquire the now-free lock and run get_trade_by_id() before
   the first call's DELETE had actually committed (commit only happens at
   Flask request teardown, well after unlock_trade() runs mid-function)
   -- under READ COMMITTED, that plain SELECT reads the last COMMITTED
   snapshot, which still shows the row. The second call would then run
   the entire resource/gold transfer a second time for one trade offer.

Fixed by (a) moving delete_trade_by_id() before the lock is released, and
(b) adding FOR UPDATE to get_trade_by_id() so the real Postgres row lock
-- not the advisory lock's release timing -- is what a second racer
actually blocks on; it only unblocks once the first call's whole
transaction commits, by which point the row is genuinely gone (same
idiom get_offer_by_id() in this same file already used correctly).

This test deterministically forces the exact race window rather than
hoping real thread scheduling hits it: it tracks call order into
try_lock_trade() and makes the SECOND caller wait on an Event that fires
the instant the FIRST caller's unlock_trade() runs -- landing the second
call's get_trade_by_id() attempt in precisely the window between "lock
released" and "transaction committed" that this bug exploited, while
still calling the real, unmodified accept_trade() view function directly.
"""
import threading
import uuid
from unittest.mock import patch

import bcrypt
import pytest

from database import get_db_connection

TEST_PASSWORD = bcrypt.hashpw(b"correct-horse-battery", bcrypt.gensalt()).decode()

TRADE_AMOUNT = 10
TRADE_PRICE = 100
INITIAL_OFFEREE_RESOURCE = 2 * TRADE_AMOUNT  # enough for a double-process to fully "succeed" twice


def _create_user(db, suffix):
    username = f"accepttrade_{suffix}_{uuid.uuid4().hex[:8]}"
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
    return user_id


@pytest.fixture
def buy_trade():
    with get_db_connection() as conn:
        db = conn.cursor()
        offerer_id = _create_user(db, "offerer")
        offeree_id = _create_user(db, "offeree")

        db.execute(
            """
            INSERT INTO user_economy (user_id, resource_id, quantity)
            SELECT %s, resource_id, %s FROM resource_dictionary WHERE name = 'lumber'
            """,
            (offeree_id, INITIAL_OFFEREE_RESOURCE),
        )
        db.execute(
            """
            INSERT INTO trades (type, offerer, offeree, resource, amount, price)
            VALUES ('buy', %s, %s, 'lumber', %s, %s)
            RETURNING offer_id
            """,
            (offerer_id, offeree_id, TRADE_AMOUNT, TRADE_PRICE),
        )
        trade_id = db.fetchone()[0]
        conn.commit()

    yield {"offerer_id": offerer_id, "offeree_id": offeree_id, "trade_id": trade_id}

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("DELETE FROM trades WHERE offer_id = %s", (trade_id,))
        db.execute("DELETE FROM user_economy WHERE user_id IN (%s, %s)", (offerer_id, offeree_id))
        db.execute("DELETE FROM stats WHERE id IN (%s, %s)", (offerer_id, offeree_id))
        db.execute("DELETE FROM users WHERE id IN (%s, %s)", (offerer_id, offeree_id))
        conn.commit()


def test_two_concurrent_accepts_process_trade_only_once(buy_trade):
    from app import app
    import app_core.market.routes as market_routes

    offerer_id = buy_trade["offerer_id"]
    offeree_id = buy_trade["offeree_id"]
    trade_id = buy_trade["trade_id"]

    real_try_lock_trade = market_routes.try_lock_trade
    real_unlock_trade = market_routes.unlock_trade

    order_lock = threading.Lock()
    call_order = []
    first_unlocked = threading.Event()

    def _patched_try_lock_trade(db, tid):
        with order_lock:
            my_index = len(call_order)
            call_order.append(my_index)
        if my_index == 1:
            first_unlocked.wait(timeout=5)
        return real_try_lock_trade(db, tid)

    def _patched_unlock_trade(db, tid):
        result = real_unlock_trade(db, tid)
        first_unlocked.set()
        return result

    barrier = threading.Barrier(2)
    errors = []

    def _run(slot):
        try:
            with app.test_request_context(
                f"/accept_trade/{trade_id}", method="POST"
            ):
                from flask import session

                session["user_id"] = offeree_id
                barrier.wait(timeout=5)
                market_routes.accept_trade(str(trade_id))
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=_run, args=(i,)) for i in range(2)]
    with patch.object(
        market_routes, "try_lock_trade", _patched_try_lock_trade
    ), patch.object(
        market_routes, "unlock_trade", _patched_unlock_trade
    ):
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

    assert not errors, f"racer thread(s) raised: {errors}"

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT gold FROM stats WHERE id = %s", (offeree_id,))
        offeree_gold = db.fetchone()[0]
        db.execute(
            """
            SELECT COALESCE(ue.quantity, 0) FROM resource_dictionary rd
            LEFT JOIN user_economy ue ON ue.resource_id = rd.resource_id AND ue.user_id = %s
            WHERE rd.name = 'lumber'
            """,
            (offeree_id,),
        )
        offeree_lumber = db.fetchone()[0]

    assert offeree_gold == TRADE_AMOUNT * TRADE_PRICE, (
        f"offeree gold is {offeree_gold}, expected exactly {TRADE_AMOUNT * TRADE_PRICE} "
        f"(one trade acceptance) -- a higher value means the same trade was "
        f"processed twice"
    )
    assert offeree_lumber == INITIAL_OFFEREE_RESOURCE - TRADE_AMOUNT, (
        f"offeree lumber is {offeree_lumber}, expected exactly "
        f"{INITIAL_OFFEREE_RESOURCE - TRADE_AMOUNT} -- a lower value means the "
        f"resource side of the trade was also processed twice"
    )
