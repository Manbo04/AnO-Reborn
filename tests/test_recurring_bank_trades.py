"""Recurring coalition bank trades (Kurai, #suggestions 2026-09-26; migration
0086). Pure scheduling helpers + real-DB scenario tests of the tick.

DB tests need a throwaway local Postgres (`env -u DATABASE_PUBLIC_URL
DATABASE_URL=<local>`); the `coalition` fixture removes every row it creates
(users cascade their recurring trades and runs).
"""

import os
import threading
from datetime import datetime, timedelta, timezone

import pytest

from app_core.game_ticks.recurring_bank_trades import next_run_after, state_after_run

UTC = timezone.utc


# ------------------------------------------------------------------ pure

@pytest.mark.no_server
def test_next_run_keeps_cadence_and_never_bursts():
    t0 = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
    assert next_run_after(t0, 24, t0 + timedelta(minutes=10)) == t0 + timedelta(hours=24)
    # tick was down for 3 days: restart from now, no catch-up burst
    now = t0 + timedelta(days=3)
    assert next_run_after(t0, 6, now) == now + timedelta(hours=6)


@pytest.mark.no_server
def test_state_after_run():
    assert state_after_run("success", 0, None, 2, 3) == (1, 0, "active")
    assert state_after_run("success", 4, 5, 0, 3) == (5, 0, "completed")
    assert state_after_run("member_short", 1, 5, 0, 3) == (1, 1, "active")
    assert state_after_run("bank_short", 1, 5, 2, 3) == (1, 3, "paused")


# ------------------------------------------------------------------- DB

needs_db = pytest.mark.skipif(
    not os.getenv("DATABASE_PUBLIC_URL") and not os.getenv("DATABASE_URL"),
    reason="Requires Postgres",
)

if os.getenv("DATABASE_URL") or os.getenv("DATABASE_PUBLIC_URL"):
    from test_coalition_qol_wishlist import coalition  # noqa: F401  (fixture)


def _db():
    from database import get_db_connection
    return get_db_connection()


def _one(sql, params=()):
    with _db() as conn:
        db = conn.cursor()
        db.execute(sql, params)
        row = db.fetchone()
        conn.commit()
        return row


def _exec(sql, params=()):
    with _db() as conn:
        conn.cursor().execute(sql, params)
        conn.commit()


def _call(fn, *args, **kw):
    with _db() as conn:
        db = conn.cursor()
        out = fn(db, *args, **kw)
        conn.commit()
        return out


def _gold(uid):
    return int(_one("SELECT gold FROM stats WHERE id=%s", (uid,))[0])


def _steel(uid):
    row = _one(
        "SELECT ue.quantity FROM user_economy ue JOIN resource_dictionary r "
        "ON r.resource_id = ue.resource_id WHERE ue.user_id=%s AND r.name='steel'",
        (uid,),
    )
    return int(row[0]) if row else 0


def _bank(col):
    money, steel = _one("SELECT money, steel FROM colBanks WHERE colId=%s", (col,))
    return int(money or 0), int(steel or 0)


def _trade(rec_id):
    return _one(
        "SELECT status, repetitions_done, consecutive_failures, next_execution_at "
        "FROM col_bank_recurring_trades WHERE id=%s",
        (rec_id,),
    )


def _make_due(rec_id):
    _exec(
        "UPDATE col_bank_recurring_trades SET next_execution_at = NOW() - INTERVAL '1 minute' WHERE id=%s",
        (rec_id,),
    )


def _propose_and_approve(c, max_reps=None, give_amt=100_000, want_amt=10):
    """Member gives money, bank gives steel, daily."""
    from app_core.coalition_bank import services as bank

    ok, msg = _call(
        bank.propose_recurring_trade, c["member"], c["col_id"],
        "money", str(give_amt), "steel", str(want_amt), "24", max_reps, "test",
    )
    assert ok, msg
    rec_id = _one(
        "SELECT MAX(id) FROM col_bank_recurring_trades WHERE user_id=%s", (c["member"],)
    )[0]
    # plain member can't approve
    ok, _, _ = _call(bank.accept_recurring_trade, c["member2"], rec_id)
    assert not ok
    ok, msg, _ = _call(bank.accept_recurring_trade, c["banker"], rec_id)
    assert ok, msg
    return rec_id


@needs_db
def test_propose_validation(coalition):
    from app_core.coalition_bank import services as bank

    c = coalition
    bad = [
        ("money", "1", "steel", "1", "5", None),       # interval not offered
        ("money", "1", "money", "1", "24", None),      # same resource
        ("money", "0", "steel", "1", "24", None),      # zero amount
        ("money", "1", "steel", "1", "24", "0"),       # zero repetitions
        ("nukes", "1", "steel", "1", "24", None),      # not a bank resource
    ]
    for args in bad:
        ok, _ = _call(bank.propose_recurring_trade, c["member"], c["col_id"], *args)
        assert not ok, args
    for _ in range(bank.MAX_RECURRING_PER_MEMBER):
        ok, msg = _call(bank.propose_recurring_trade, c["member"], c["col_id"], "money", "1", "steel", "1", "24", None)
        assert ok, msg
    ok, msg = _call(bank.propose_recurring_trade, c["member"], c["col_id"], "money", "1", "steel", "1", "24", None)
    assert not ok and "already have" in msg


@needs_db
def test_tick_executes_once_per_occurrence(coalition):
    from app_core.game_ticks.recurring_bank_trades import run_recurring_bank_trades

    c = coalition
    col = c["col_id"]
    _exec("UPDATE colBanks SET steel = 25 WHERE colId=%s", (col,))
    rec_id = _propose_and_approve(c)
    gold0, steel0, bank0 = _gold(c["member"]), _steel(c["member"]), _bank(col)

    run_recurring_bank_trades()
    status, reps, fails, nxt = _trade(rec_id)
    assert (status, reps, fails) == ("active", 1, 0)
    assert nxt > datetime.now(UTC) + timedelta(hours=23)
    assert _gold(c["member"]) == gold0 - 100_000
    assert _steel(c["member"]) == steel0 + 10
    assert _bank(col) == (bank0[0] + 100_000, bank0[1] - 10)
    # both legs logged as trade legs
    kinds = _one(
        "SELECT array_agg(kind || ':' || direction ORDER BY direction) FROM col_bank_transactions "
        "WHERE coalition_id=%s AND user_id=%s",
        (col, c["member"]),
    )[0]
    assert kinds == ["trade:deposit", "trade:withdraw"]

    # not due again -> a second tick does nothing
    run_recurring_bank_trades()
    assert _trade(rec_id)[1] == 1
    assert _gold(c["member"]) == gold0 - 100_000


@needs_db
def test_duplicate_occurrence_is_rejected_and_rolled_back(coalition):
    from app_core.game_ticks.recurring_bank_trades import run_recurring_bank_trades

    c = coalition
    _exec("UPDATE colBanks SET steel = 25 WHERE colId=%s", (c["col_id"],))
    rec_id = _propose_and_approve(c)
    scheduled = _trade(rec_id)[3]
    # Pretend this exact occurrence already ran (e.g. a crashed overlapping tick).
    _exec(
        "INSERT INTO col_bank_recurring_trade_runs (recurring_trade_id, scheduled_for, outcome) "
        "VALUES (%s, %s, 'success')",
        (rec_id, scheduled),
    )
    gold0, bank0 = _gold(c["member"]), _bank(c["col_id"])
    run_recurring_bank_trades()
    assert _gold(c["member"]) == gold0
    assert _bank(c["col_id"]) == bank0
    assert _trade(rec_id)[1] == 0


@needs_db
def test_concurrent_ticks_execute_once(coalition):
    from app_core.game_ticks.recurring_bank_trades import _run_one

    c = coalition
    _exec("UPDATE colBanks SET steel = 25 WHERE colId=%s", (c["col_id"],))
    rec_id = _propose_and_approve(c)
    gold0 = _gold(c["member"])
    results = []
    barrier = threading.Barrier(2)

    def worker():
        with _db() as conn:
            db = conn.cursor()
            barrier.wait()
            results.append(_run_one(db, rec_id))
            conn.commit()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(results) == 2
    assert results.count("success") == 1
    assert _gold(c["member"]) == gold0 - 100_000


@needs_db
def test_short_sides_skip_then_pause_then_resume(coalition):
    from app_core.coalition_bank import services as bank
    from app_core.game_ticks.recurring_bank_trades import run_recurring_bank_trades

    c = coalition
    col = c["col_id"]
    _exec("UPDATE colBanks SET steel = 0 WHERE colId=%s", (col,))
    rec_id = _propose_and_approve(c)
    gold0, bank0 = _gold(c["member"]), _bank(col)

    run_recurring_bank_trades()  # bank short: member's money must come back
    assert _gold(c["member"]) == gold0 and _bank(col) == bank0
    assert _trade(rec_id)[:3] == ("active", 0, 1)

    _exec("UPDATE stats SET gold = 5 WHERE id=%s", (c["member"],))
    _exec("UPDATE colBanks SET steel = 100 WHERE colId=%s", (col,))
    _make_due(rec_id)
    run_recurring_bank_trades()  # member short
    assert _trade(rec_id)[:3] == ("active", 0, 2)
    assert _bank(col)[1] == 100

    _make_due(rec_id)
    run_recurring_bank_trades()  # third miss -> paused
    assert _trade(rec_id)[:3] == ("paused", 0, 3)
    outcomes = _one(
        "SELECT array_agg(outcome ORDER BY id) FROM col_bank_recurring_trade_runs WHERE recurring_trade_id=%s",
        (rec_id,),
    )[0]
    assert outcomes == ["bank_short", "member_short", "member_short"]
    assert _one("SELECT COUNT(*) FROM news WHERE destination_id=%s AND message LIKE %s",
                (c["member"], f"%#{rec_id}%paused%"))[0] == 1

    _make_due(rec_id)
    run_recurring_bank_trades()  # paused trades don't run
    assert _trade(rec_id)[1:3] == (0, 3)

    _exec("UPDATE stats SET gold = 5000000 WHERE id=%s", (c["member"],))
    ok, msg, _ = _call(bank.resume_recurring_trade, c["member"], rec_id)
    assert ok, msg
    run_recurring_bank_trades()
    assert _trade(rec_id)[:3] == ("active", 1, 0)


@needs_db
def test_max_repetitions_completes_and_cancel_rules(coalition):
    from app_core.coalition_bank import services as bank
    from app_core.game_ticks.recurring_bank_trades import run_recurring_bank_trades

    c = coalition
    _exec("UPDATE colBanks SET steel = 100 WHERE colId=%s", (c["col_id"],))
    rec_id = _propose_and_approve(c, max_reps="1")
    run_recurring_bank_trades()
    status, reps, _, nxt = _trade(rec_id)
    assert (status, reps, nxt) == ("completed", 1, None)
    ok, _, _ = _call(bank.decline_recurring_trade, c["member"], rec_id, cancel=True)
    assert not ok  # already ended

    rec2 = _propose_and_approve(c)
    ok, _, _ = _call(bank.decline_recurring_trade, c["member2"], rec2, cancel=True)
    assert not ok  # someone else's, not an officer
    ok, _, _ = _call(bank.decline_recurring_trade, c["deputy"], rec2, cancel=True)
    assert ok  # officer side can cancel
    assert _trade(rec2)[0] == "cancelled"
    _make_due(rec2)
    gold0 = _gold(c["member"])
    run_recurring_bank_trades()
    assert _gold(c["member"]) == gold0


@needs_db
def test_member_leaving_cancels_trade(coalition):
    from database import get_coalition_members_table
    from app_core.game_ticks.recurring_bank_trades import run_recurring_bank_trades

    c = coalition
    rec_id = _propose_and_approve(c)
    tbl = get_coalition_members_table()
    _exec(f"DELETE FROM {tbl} WHERE userid=%s", (c["member"],))
    gold0 = _gold(c["member"])
    run_recurring_bank_trades()
    assert _trade(rec_id)[0] == "cancelled"
    assert _gold(c["member"]) == gold0


@needs_db
def test_bank_trades_page_renders_recurring(client, coalition):
    c = coalition
    _exec("UPDATE colBanks SET steel = 100 WHERE colId=%s", (c["col_id"],))
    rec_id = _propose_and_approve(c)
    with client.session_transaction() as sess:
        sess["user_id"] = c["banker"]
    body = client.get(f"/coalition/{c['col_id']}/bank-trades").get_data(as_text=True)
    assert "Set up a recurring trade" in body
    assert f"#{rec_id}" in body and "Approve" not in body  # already approved
    assert "Runs done: 0" in body

    # route-level cancel by the member
    with client.session_transaction() as sess:
        sess["user_id"] = c["member"]
    r = client.post(
        f"/coalition/bank-trades/recurring/{rec_id}/cancel",
        headers={"Origin": "http://localhost", "Referer": "http://localhost/"},
    )
    assert r.status_code in (302, 303)
    assert _trade(rec_id)[0] == "cancelled"
