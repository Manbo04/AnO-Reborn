"""Regression test for a real double-grant race found live 2026-09-23 while
auditing app_core/coalitions/ during the account cross-contamination
investigation (unrelated to that bug, found along the way).

accept_bank_request() read the colBanksRequests row with a plain SELECT (no
row lock), withdrew the resource from the coalition bank, and only THEN
deleted the request row. If two bankers (or one banker double-clicking /
two tabs) accepted the SAME request concurrently, both could read the row
before either deleted it -- and if the bank held enough funds for two
payouts, both withdraw() calls would succeed independently, crediting the
requester twice for one request. Fixed by adding FOR UPDATE to the initial
SELECT, serializing concurrent accepts on that row (same idiom as
trade_agreements/repositories.py's lock_active_agreement()).

Uses real concurrency (two threads, each with its own real Flask request
context and DB connection, a barrier forcing overlap) against the real
local ano_staging database, calling the actual unmodified
accept_bank_request() function directly rather than through the full HTTP
test client -- going through the full WSGI/decorator/rate-limiter stack
introduced enough scheduling variance between the two threads that the
race window was not reliably hit (confirmed while developing this test).
Calling the view function directly inside app.test_request_context() still
exercises the real production code and the real request-scoped DB
connection/transaction (get_request_cursor), just without the unrelated
HTTP-layer overhead -- the same style already used successfully by this
session's test_referral_milestone_no_double_payout.py.
"""
import threading
import uuid

import bcrypt
import pytest

from database import get_db_connection

TEST_PASSWORD = bcrypt.hashpw(b"correct-horse-battery", bcrypt.gensalt()).decode()

BANK_MONEY = 5_000_000
REQUEST_AMOUNT = 1_000_000


@pytest.fixture
def coalition_bank_request():
    with get_db_connection() as conn:
        db = conn.cursor()
        suffix = uuid.uuid4().hex[:8]

        def _create_user(role_suffix):
            username = f"colbanktest_{role_suffix}_{suffix}"
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

        banker_id = _create_user("banker")
        requester_id = _create_user("requester")

        db.execute(
            """
            INSERT INTO colNames (name, type, date)
            VALUES (%s, 'coalition', '2026-09-23')
            RETURNING id
            """,
            (f"ColBankTest {suffix}",),
        )
        coalition_id = db.fetchone()[0]

        db.execute(
            "INSERT INTO coalitions_legacy (colid, userid, role) VALUES (%s, %s, 'banker')",
            (coalition_id, banker_id),
        )
        db.execute(
            "INSERT INTO coalitions_legacy (colid, userid, role) VALUES (%s, %s, 'member')",
            (coalition_id, requester_id),
        )
        db.execute(
            "INSERT INTO colBanks (colId, money) VALUES (%s, %s)",
            (coalition_id, BANK_MONEY),
        )
        db.execute(
            "INSERT INTO colBanksRequests (reqId, colId, amount, resource) VALUES (%s, %s, %s, 'money') RETURNING id",
            (requester_id, coalition_id, REQUEST_AMOUNT),
        )
        bank_request_id = db.fetchone()[0]
        conn.commit()

    yield {
        "banker_id": banker_id,
        "requester_id": requester_id,
        "coalition_id": coalition_id,
        "bank_request_id": bank_request_id,
    }

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("DELETE FROM colBanksRequests WHERE colId = %s", (coalition_id,))
        db.execute("DELETE FROM colBanks WHERE colId = %s", (coalition_id,))
        db.execute("DELETE FROM coalitions_legacy WHERE colid = %s", (coalition_id,))
        db.execute("DELETE FROM colNames WHERE id = %s", (coalition_id,))
        db.execute("DELETE FROM stats WHERE id IN (%s, %s)", (banker_id, requester_id))
        db.execute("DELETE FROM users WHERE id IN (%s, %s)", (banker_id, requester_id))
        conn.commit()


def test_two_concurrent_accepts_pay_out_only_once(coalition_bank_request):
    from app import app
    from app_core.coalitions.routes import accept_bank_request

    banker_id = coalition_bank_request["banker_id"]
    requester_id = coalition_bank_request["requester_id"]
    coalition_id = coalition_bank_request["coalition_id"]
    bank_request_id = coalition_bank_request["bank_request_id"]

    barrier = threading.Barrier(2)
    results = [None, None]
    errors = []

    def _racer(slot):
        try:
            with app.test_request_context(
                f"/accept_bank_request/{bank_request_id}", method="POST"
            ):
                from flask import session

                session["user_id"] = banker_id
                barrier.wait(timeout=5)
                results[slot] = accept_bank_request(bank_request_id)
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=_racer, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors, f"racer thread(s) raised: {errors}"

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT gold FROM stats WHERE id = %s", (requester_id,))
        requester_gold = db.fetchone()[0]
        db.execute("SELECT money FROM colBanks WHERE colId = %s", (coalition_id,))
        bank_money = db.fetchone()[0]
        db.execute(
            "SELECT COUNT(*) FROM colBanksRequests WHERE id = %s", (bank_request_id,)
        )
        remaining_requests = db.fetchone()[0]

    assert requester_gold == REQUEST_AMOUNT, (
        f"requester gold is {requester_gold}, expected exactly one payout "
        f"({REQUEST_AMOUNT}) -- a higher value means the bank request was "
        f"accepted and paid out twice"
    )
    assert bank_money == BANK_MONEY - REQUEST_AMOUNT, (
        f"coalition bank money is {bank_money}, expected exactly one "
        f"withdrawal deducted"
    )
    assert remaining_requests == 0, "the bank request row should be deleted after acceptance"
