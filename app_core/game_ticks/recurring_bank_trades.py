"""Tick for recurring coalition bank trades (Kurai, #suggestions 2026-09-26;
schema in migration 0086, services in app_core/coalition_bank/services.py).

Runs every 15 minutes from celery beat. Each due trade is handled in its OWN
transaction so one bad row can't roll back the others:

  1. lock the trade row (FOR UPDATE SKIP LOCKED, re-checking it's still
     active and due) -- a second overlapping tick just skips it;
  2. move both sides with conditional UPDATEs (member first, then the bank,
     inside a savepoint so a short bank undoes the member's side);
  3. record the occurrence in col_bank_recurring_trade_runs, whose
     UNIQUE (recurring_trade_id, scheduled_for) makes executing the same
     occurrence twice impossible even if the row lock were bypassed;
  4. advance next_execution_at by the interval (never into a backlog burst
     after downtime), count repetitions / consecutive failures, complete or
     auto-pause as needed, and notify.

Nothing is minted: every unit the member receives comes out of colBanks and
every unit the bank receives comes out of the member's stockpile.
"""
from datetime import datetime, timedelta, timezone

from app_core.game_ticks.common import handle_exception
from app_core.game_ticks.locks import try_pg_advisory_lock

TASK_NAME = "recurring_bank_trades"
ADVISORY_LOCK_ID = 9015
MAX_TRADES_PER_RUN = 500


# ------------------------------------------------------------------ pure

def next_run_after(scheduled_for, interval_hours, now):
    """The next occurrence after `scheduled_for`. If the tick was down long
    enough that it's already in the past, restart the cadence from `now`
    instead of firing a burst of catch-up trades."""
    step = timedelta(hours=int(interval_hours))
    nxt = scheduled_for + step
    return nxt if nxt > now else now + step


def state_after_run(outcome, repetitions_done, max_repetitions, consecutive_failures, max_failures):
    """(repetitions_done, consecutive_failures, status) after one occurrence.
    A skipped occurrence doesn't count toward max_repetitions."""
    if outcome == "success":
        reps = repetitions_done + 1
        if max_repetitions is not None and reps >= max_repetitions:
            return reps, 0, "completed"
        return reps, 0, "active"
    fails = consecutive_failures + 1
    return repetitions_done, fails, ("paused" if fails >= max_failures else "active")


# ------------------------------------------------------------------- tick

def run_recurring_bank_trades(now=None):
    """Returns {"success": n, "member_short": n, "bank_short": n, "cancelled": n}."""
    from database import get_db_connection

    counts = {"success": 0, "member_short": 0, "bank_short": 0, "cancelled": 0}
    with get_db_connection() as conn:
        # One runner at a time (xact lock, released on the first commit below;
        # after that the per-row lock + unique run row keep things safe).
        if not try_pg_advisory_lock(conn, ADVISORY_LOCK_ID, TASK_NAME):
            return counts
        db = conn.cursor()
        db.execute(
            """
            SELECT id FROM col_bank_recurring_trades
            WHERE status = 'active' AND next_execution_at <= NOW()
            ORDER BY next_execution_at
            LIMIT %s
            """,
            (MAX_TRADES_PER_RUN,),
        )
        due_ids = [r[0] for r in db.fetchall()]
        conn.commit()

        for rec_id in due_ids:
            try:
                outcome = _run_one(db, rec_id, now)
                conn.commit()
                if outcome:
                    counts[outcome] += 1
            except Exception as e:  # one broken row must not stop the rest
                conn.rollback()
                handle_exception(e, f"{TASK_NAME}#{rec_id}")
    return counts


def _run_one(db, rec_id, now=None):
    from app_core.coalition_bank import services as bank

    db.execute(
        """
        SELECT coalition_id, user_id, give_resource, give_amount, want_resource, want_amount,
               interval_hours, max_repetitions, repetitions_done, consecutive_failures,
               next_execution_at
        FROM col_bank_recurring_trades
        WHERE id = %s AND status = 'active' AND next_execution_at <= NOW()
        FOR UPDATE SKIP LOCKED
        """,
        (rec_id,),
    )
    row = db.fetchone()
    if not row:
        return None  # handled by someone else, cancelled, or no longer due
    (col_id, user_id, give_res, give_amt, want_res, want_amt, interval,
     max_reps, reps_done, fails, scheduled_for) = row
    now = now or datetime.now(timezone.utc)
    summary = bank._recurring_summary(give_amt, give_res, want_amt, want_res)

    if give_res not in bank.BANK_RESOURCES or want_res not in bank.BANK_RESOURCES:
        return _end(db, rec_id, "cancelled", [user_id], f"Recurring bank trade #{rec_id} was cancelled (invalid resource).")
    if not bank.get_role(db, user_id, col_id):
        return _end(
            db, rec_id, "cancelled", [user_id],
            f"Your recurring bank trade #{rec_id} was cancelled because you left the coalition.",
        )

    db.execute("SAVEPOINT recurring_trade_move")
    if not bank._take_from_player(db, user_id, give_res, give_amt):
        outcome = "member_short"
        db.execute("ROLLBACK TO SAVEPOINT recurring_trade_move")
    else:
        db.execute(
            f"UPDATE colBanks SET {want_res} = {want_res} - %s WHERE colId=%s AND {want_res} >= %s RETURNING colId",
            (want_amt, col_id, want_amt),
        )
        if not db.fetchone():
            outcome = "bank_short"
            db.execute("ROLLBACK TO SAVEPOINT recurring_trade_move")  # member's side goes back
        else:
            outcome = "success"
            db.execute(f"UPDATE colBanks SET {give_res} = {give_res} + %s WHERE colId=%s", (give_amt, col_id))
            bank._give_to_player(db, user_id, want_res, want_amt)
            bank._log_bank_txn(db, col_id, user_id, user_id, give_res, give_amt, "deposit", kind="trade")
            bank._log_bank_txn(db, col_id, user_id, user_id, want_res, want_amt, "withdraw", kind="trade")
    db.execute("RELEASE SAVEPOINT recurring_trade_move")

    db.execute(
        """
        INSERT INTO col_bank_recurring_trade_runs (recurring_trade_id, scheduled_for, outcome)
        VALUES (%s, %s, %s)
        ON CONFLICT (recurring_trade_id, scheduled_for) DO NOTHING
        RETURNING id
        """,
        (rec_id, scheduled_for, outcome),
    )
    if not db.fetchone():
        # This occurrence was already recorded: undo everything we just did.
        raise RuntimeError(f"recurring trade {rec_id} occurrence {scheduled_for} already executed")

    reps, new_fails, status = state_after_run(
        outcome, reps_done, max_reps, fails, bank.RECURRING_MAX_FAILURES
    )
    db.execute(
        """
        UPDATE col_bank_recurring_trades
        SET repetitions_done=%s, consecutive_failures=%s, status=%s,
            next_execution_at=%s, last_executed_at=NOW(),
            ended_at = CASE WHEN %s = 'completed' THEN NOW() ELSE ended_at END
        WHERE id=%s
        """,
        (reps, new_fails, status,
         None if status == "completed" else next_run_after(scheduled_for, interval, now),
         status, rec_id),
    )

    officers = bank.get_officer_ids(db, col_id, exclude=user_id)
    if outcome == "member_short":
        msg = (f"Recurring bank trade #{rec_id} ({summary}) was skipped: you didn't have "
               f"{give_amt:,} {bank.resource_label(give_res).lower()}.")
        recipients = [user_id]
    elif outcome == "bank_short":
        msg = (f"Recurring bank trade #{rec_id} ({summary}) was skipped: the coalition bank didn't have "
               f"{want_amt:,} {bank.resource_label(want_res).lower()}.")
        recipients = [user_id] + officers
    elif status == "completed":
        msg = f"Recurring bank trade #{rec_id} ({summary}) finished all {reps:,} runs."
        recipients = [user_id]
    else:
        msg = None
        recipients = []
    if status == "paused":
        msg += (f" It failed {new_fails} times in a row, so it's paused. "
                f"Resume it from Bank trades once there's enough.")
        recipients = [user_id] + officers
    if msg:
        bank._news(db, recipients, msg)
    return outcome


def _end(db, rec_id, status, notify, message):
    from app_core.coalition_bank import services as bank

    db.execute(
        """
        UPDATE col_bank_recurring_trades
        SET status=%s, ended_at=NOW(), next_execution_at=NULL
        WHERE id=%s
        """,
        (status, rec_id),
    )
    bank._news(db, notify, message)
    return "cancelled"
