"""Hourly tick: garnishes interest on every active national loan directly
from the borrower's gold, compounding any shortfall into the loan balance.

Unlike letting interest silently accrue as a displayed number, this tick
actually takes the money each hour -- so an unpaid loan has a real, felt
cost (steadily draining a nation's treasury) rather than being free money
with no consequence for ignoring it. See app_core/loans/ for the
take-loan/repay-loan user-facing flow this tick backs.

Standalone tick with its own advisory lock and task_runs row, same pattern
as unit_production.py / disasters.py.
"""
from app_core.game_ticks.common import should_skip_task, handle_exception, log_verbose
from app_core.game_ticks.locks import try_pg_advisory_lock, release_pg_advisory_lock

TASK_NAME = "loan_interest"
ADVISORY_LOCK_ID = 9013


def compute_interest_charge(balance, interest_rate, available_gold):
    """Pure helper (no DB) -- given a loan's balance/rate and the borrower's
    current gold, returns (amount_garnished_from_gold, new_balance).
    A shortfall (gold < interest due) compounds into the balance."""
    interest_due = balance * interest_rate
    if interest_due <= 0:
        return 0, balance

    garnished = min(interest_due, available_gold)
    shortfall = interest_due - garnished
    new_balance = balance + shortfall
    return garnished, new_balance


def run_loan_interest():
    from database import get_db_connection

    with get_db_connection() as conn:
        if not try_pg_advisory_lock(conn, ADVISORY_LOCK_ID, TASK_NAME):
            return

        try:
            db = conn.cursor()
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS task_runs (
                    task_name TEXT PRIMARY KEY,
                    last_run TIMESTAMP WITH TIME ZONE
                )
                """
            )
            db.execute(
                "INSERT INTO task_runs (task_name, last_run) VALUES (%s, NULL) "
                "ON CONFLICT DO NOTHING",
                (TASK_NAME,),
            )
            db.execute(
                "SELECT last_run FROM task_runs WHERE task_name=%s FOR UPDATE",
                (TASK_NAME,),
            )
            row = db.fetchone()
            if should_skip_task(row, TASK_NAME):
                return

            db.execute(
                """
                SELECT ul.id, ul.user_id, ul.balance, ul.interest_rate, s.gold
                FROM user_loans ul
                JOIN stats s ON s.id = ul.user_id
                WHERE ul.status = 'active'
                """
            )
            loans = db.fetchall()

            for loan_id, user_id, balance, interest_rate, gold in loans:
                balance = float(balance)
                interest_rate = float(interest_rate)
                gold = float(gold) if gold is not None else 0.0

                garnished, new_balance = compute_interest_charge(
                    balance, interest_rate, gold
                )

                if garnished > 0:
                    db.execute(
                        "UPDATE stats SET gold = GREATEST(0, gold - %s) WHERE id = %s",
                        (garnished, user_id),
                    )
                if new_balance != balance:
                    db.execute(
                        "UPDATE user_loans SET balance = %s WHERE id = %s",
                        (new_balance, loan_id),
                    )

                log_verbose(
                    f"LOAN_INTEREST | USER: {user_id} | loan={loan_id} "
                    f"garnished={garnished:.2f} balance={balance:.2f}->{new_balance:.2f}"
                )

            db.execute(
                "UPDATE task_runs SET last_run = now() WHERE task_name=%s",
                (TASK_NAME,),
            )
        except Exception as e:
            handle_exception(e, TASK_NAME)
            raise
        finally:
            try:
                release_pg_advisory_lock(conn, ADVISORY_LOCK_ID)
            except Exception:
                pass
