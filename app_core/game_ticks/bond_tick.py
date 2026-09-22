"""Daily tick for the player-to-player Bonds market (app_core/bonds/):
garnishes each active bond's daily interest from the issuer straight to the
lender, optionally amortizes principal into escrow for auto_escrow bonds,
force-defaults a bond after too many missed interest payments instead of
waiting for a maturity cliff, resolves bonds that reach maturity, and keeps
collecting any unpaid shortfall from a defaulted issuer afterwards so that
defaulting is never free money for the borrower.

Same standalone-tick shape as loan_interest.py / disasters.py: its own
advisory lock and task_runs row.
"""
from datetime import datetime, timezone

import variables

from app_core.game_ticks.common import should_skip_task, handle_exception, log_verbose
from app_core.game_ticks.locks import try_pg_advisory_lock, release_pg_advisory_lock

TASK_NAME = "bond_tick"
ADVISORY_LOCK_ID = 9014


def compute_daily_bond_charge(principal, daily_interest_rate, auto_escrow, term_days, available_gold):
    """Pure helper (no DB). Given a bond's terms and the issuer's currently
    available gold, returns (interest_garnished, escrow_contribution,
    missed_interest: bool).

    Interest is always prioritized over the optional principal escrow
    contribution -- a lender should never go unpaid on interest because the
    issuer chose to auto-escrow principal too.
    """
    interest_due = principal * daily_interest_rate
    principal_installment_due = (principal / term_days) if (auto_escrow and term_days > 0) else 0

    interest_garnished = min(interest_due, available_gold)
    remaining_gold = available_gold - interest_garnished
    escrow_garnished = min(principal_installment_due, remaining_gold)

    missed_interest = interest_garnished < interest_due
    return interest_garnished, escrow_garnished, missed_interest


def compute_maturity_settlement(principal, escrowed_principal, available_gold):
    """Pure helper: at maturity, the issuer owes whatever principal hasn't
    already been escrowed, as a lump sum. Returns (garnished_now, shortfall)
    -- shortfall > 0 means this bond defaults for that remaining amount."""
    remaining_due = max(0.0, principal - escrowed_principal)
    garnished = min(remaining_due, available_gold)
    shortfall = remaining_due - garnished
    return garnished, shortfall


def run_bond_tick():
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

            _process_active_bonds(db)
            _process_defaulted_shortfalls(db)

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


def _process_active_bonds(db):
    db.execute(
        """
        SELECT b.id, b.issuer_id, b.lender_id, b.principal, b.daily_interest_rate,
               b.term_days, b.auto_escrow, b.escrowed_principal, b.default_strikes,
               b.matures_at, s.gold
        FROM bonds b
        JOIN stats s ON s.id = b.issuer_id
        WHERE b.status = 'active'
        """
    )
    bonds = db.fetchall()
    now = datetime.now(timezone.utc)

    for (bond_id, issuer_id, lender_id, principal, daily_interest_rate, term_days,
         auto_escrow, escrowed_principal, default_strikes, matures_at, gold) in bonds:
        principal = float(principal)
        daily_interest_rate = float(daily_interest_rate)
        escrowed_principal = float(escrowed_principal)
        gold = float(gold) if gold is not None else 0.0

        interest_garnished, escrow_garnished, missed_interest = compute_daily_bond_charge(
            principal, daily_interest_rate, auto_escrow, term_days, gold
        )
        total_garnished = interest_garnished + escrow_garnished

        if total_garnished > 0:
            db.execute(
                "UPDATE stats SET gold = GREATEST(0, gold - %s) WHERE id = %s",
                (total_garnished, issuer_id),
            )
        if interest_garnished > 0:
            db.execute(
                "UPDATE stats SET gold = gold + %s WHERE id = %s",
                (interest_garnished, lender_id),
            )

        new_escrowed = escrowed_principal + escrow_garnished
        new_strikes = default_strikes + 1 if missed_interest else 0

        matured = matures_at is not None and now >= matures_at
        force_defaulted = new_strikes >= variables.BOND_MAX_DEFAULT_STRIKES

        if not matured and not force_defaulted:
            db.execute(
                """
                UPDATE bonds
                SET escrowed_principal = %s, default_strikes = %s, last_tick_at = NOW()
                WHERE id = %s
                """,
                (new_escrowed, new_strikes, bond_id),
            )
            log_verbose(
                f"BOND_TICK | bond={bond_id} issuer={issuer_id} lender={lender_id} "
                f"interest={interest_garnished:.2f} escrow+={escrow_garnished:.2f} "
                f"strikes={new_strikes}"
            )
            continue

        # Reload gold post-garnish for the lump-sum settlement below (the
        # interest/escrow UPDATE above already spent some of it).
        remaining_gold = max(0.0, gold - total_garnished)
        lump_garnished, shortfall = compute_maturity_settlement(principal, new_escrowed, remaining_gold)

        if lump_garnished > 0:
            db.execute(
                "UPDATE stats SET gold = GREATEST(0, gold - %s) WHERE id = %s",
                (lump_garnished, issuer_id),
            )
        payout_to_lender = new_escrowed + lump_garnished
        if payout_to_lender > 0:
            db.execute(
                "UPDATE stats SET gold = gold + %s WHERE id = %s",
                (payout_to_lender, lender_id),
            )

        if shortfall > 0:
            # Force-defaulted (too many missed interest payments) or
            # matured without enough gold to cover the remaining principal
            # -- either way, the unpaid amount becomes garnishment_owed,
            # which _process_defaulted_shortfalls keeps collecting from the
            # issuer going forward instead of forgiving it. This is what
            # makes a default cost the issuer something real rather than
            # being free money.
            db.execute(
                """
                UPDATE bonds
                SET status = 'defaulted', escrowed_principal = 0, default_strikes = %s,
                    garnishment_owed = %s, resolved_at = NOW(), last_tick_at = NOW()
                WHERE id = %s
                """,
                (new_strikes, shortfall, bond_id),
            )
            log_verbose(
                f"BOND_DEFAULT | bond={bond_id} issuer={issuer_id} lender={lender_id} "
                f"paid_out={payout_to_lender:.2f} shortfall={shortfall:.2f}"
            )
        else:
            db.execute(
                """
                UPDATE bonds
                SET status = 'repaid', escrowed_principal = 0, default_strikes = %s,
                    resolved_at = NOW(), last_tick_at = NOW()
                WHERE id = %s
                """,
                (new_strikes, bond_id),
            )
            log_verbose(
                f"BOND_REPAID | bond={bond_id} issuer={issuer_id} lender={lender_id} "
                f"paid_out={payout_to_lender:.2f}"
            )


def _process_defaulted_shortfalls(db):
    """Keeps garnishing a defaulted issuer's gold, daily, toward the lender
    they stiffed -- until garnishment_owed reaches zero. Without this, a
    default that happened to leave a shortfall would just write it off,
    which is exactly the "free money on default" outcome this feature
    needs to avoid."""
    db.execute(
        """
        SELECT b.id, b.issuer_id, b.lender_id, b.garnishment_owed, s.gold
        FROM bonds b
        JOIN stats s ON s.id = b.issuer_id
        WHERE b.status = 'defaulted' AND b.garnishment_owed > 0 AND b.lender_id IS NOT NULL
        """
    )
    rows = db.fetchall()

    for bond_id, issuer_id, lender_id, garnishment_owed, gold in rows:
        garnishment_owed = float(garnishment_owed)
        gold = float(gold) if gold is not None else 0.0

        garnished = min(garnishment_owed, gold)
        if garnished <= 0:
            continue

        db.execute(
            "UPDATE stats SET gold = GREATEST(0, gold - %s) WHERE id = %s",
            (garnished, issuer_id),
        )
        db.execute(
            "UPDATE stats SET gold = gold + %s WHERE id = %s",
            (garnished, lender_id),
        )
        db.execute(
            "UPDATE bonds SET garnishment_owed = garnishment_owed - %s, last_tick_at = NOW() WHERE id = %s",
            (garnished, bond_id),
        )
        log_verbose(
            f"BOND_GARNISHMENT | bond={bond_id} issuer={issuer_id} lender={lender_id} "
            f"collected={garnished:.2f} remaining={garnishment_owed - garnished:.2f}"
        )
