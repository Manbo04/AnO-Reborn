# Trade Agreements - Private recurring automatic trades between players
from helpers import login_required
from database import get_db_connection, invalidate_user_cache
from flask import request, render_template, session, redirect, flash
import variables
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Valid interval options (in hours)
VALID_INTERVALS = [1, 6, 12, 24, 48, 72, 168]  # 1h, 6h, 12h, 1d, 2d, 3d, 1 week


def get_resource_column(resource):
    """Get the database column name for a resource."""
    if resource == "money":
        return "gold"
    return resource


def check_resource_balance(cursor, user_id, resource, amount):
    """Check if user has enough of a resource. Returns (has_enough, current_balance)."""
    if resource == "money":
        cursor.execute("SELECT gold FROM stats WHERE id = %s", (user_id,))
    else:
        cursor.execute(f"SELECT {resource} FROM resources WHERE id = %s", (user_id,))

    row = cursor.fetchone()
    if not row:
        return False, 0

    current = int(row[0]) if row[0] else 0
    return current >= amount, current


def execute_trade_agreement(agreement_id, cursor=None):
    """Execute a single trade agreement. Returns (success, message)."""
    owns_connection = cursor is None

    if owns_connection:
        conn = get_db_connection().__enter__()
        db = conn.cursor()
    else:
        db = cursor
        conn = None

    try:
        # Get agreement details
        db.execute(
            """
            SELECT id, proposer_id, proposer_resource, proposer_amount,
                   receiver_id, receiver_resource, receiver_amount,
                   execution_count, max_executions, interval_hours
            FROM trade_agreements
            WHERE id = %s AND status = 'active'
            FOR UPDATE
        """,
            (agreement_id,),
        )

        agreement = db.fetchone()
        if not agreement:
            return False, "Agreement not found or not active"

        (
            aid,
            proposer_id,
            proposer_resource,
            proposer_amount,
            receiver_id,
            receiver_resource,
            receiver_amount,
            execution_count,
            max_executions,
            interval_hours,
        ) = agreement

        # Check proposer has enough resources
        has_enough, balance = check_resource_balance(
            db, proposer_id, proposer_resource, proposer_amount
        )
        if not has_enough:
            # Pause the agreement due to insufficient funds
            db.execute(
                """
                UPDATE trade_agreements
                SET status = 'paused', updated_at = now()
                WHERE id = %s
            """,
                (aid,),
            )
            if owns_connection:
                conn.commit()
            msg = (
                f"Proposer has insufficient {proposer_resource} "
                f"(has {balance}, needs {proposer_amount})"
            )
            return (False, msg)

        # Check receiver has enough resources
        has_enough, balance = check_resource_balance(
            db, receiver_id, receiver_resource, receiver_amount
        )
        if not has_enough:
            # Pause the agreement due to insufficient funds
            db.execute(
                """
                UPDATE trade_agreements
                SET status = 'paused', updated_at = now()
                WHERE id = %s
            """,
                (aid,),
            )
            if owns_connection:
                conn.commit()
            msg = (
                f"Receiver has insufficient {receiver_resource} "
                f"(has {balance}, needs {receiver_amount})"
            )
            return (False, msg)

        # Execute the trade - transfer resources
        # Proposer gives their resource to receiver
        from market import give_resource

        result = give_resource(
            proposer_id, receiver_id, proposer_resource, proposer_amount, cursor=db
        )
        if result is not True:
            return False, f"Failed to transfer {proposer_resource}: {result}"

        # Receiver gives their resource to proposer
        result = give_resource(
            receiver_id, proposer_id, receiver_resource, receiver_amount, cursor=db
        )
        if result is not True:
            return False, f"Failed to transfer {receiver_resource}: {result}"

        # Update agreement
        new_execution_count = execution_count + 1
        next_exec = datetime.utcnow() + timedelta(hours=interval_hours)

        # Check if we've hit max executions
        if max_executions and new_execution_count >= max_executions:
            db.execute(
                """
                UPDATE trade_agreements
                SET execution_count = %s, last_execution = now(),
                    next_execution = NULL, status = 'completed', updated_at = now()
                WHERE id = %s
            """,
                (new_execution_count, aid),
            )
        else:
            db.execute(
                """
                UPDATE trade_agreements
                SET execution_count = %s, last_execution = now(),
                    next_execution = %s, updated_at = now()
                WHERE id = %s
            """,
                (new_execution_count, next_exec, aid),
            )

        if owns_connection:
            conn.commit()

        # Invalidate caches
        try:
            invalidate_user_cache(proposer_id)
            invalidate_user_cache(receiver_id)
        except Exception:
            pass

        # Emit structured log for audit/metrics: trade agreement executed
        try:
            logger.info(
                "trade_agreement_executed",
                extra={
                    "agreement_id": aid,
                    "proposer_id": proposer_id,
                    "receiver_id": receiver_id,
                    "proposer_resource": proposer_resource,
                    "proposer_amount": int(proposer_amount),
                    "receiver_resource": receiver_resource,
                    "receiver_amount": int(receiver_amount),
                    "execution_count": new_execution_count,
                },
            )
        except Exception:
            pass

        return True, f"Trade executed successfully (execution #{new_execution_count})"

    except Exception as e:
        if owns_connection and conn:
            conn.rollback()
        logger.error(f"Error executing trade agreement {agreement_id}: {e}")
        return False, str(e)
    finally:
        if owns_connection and conn:
            try:
                # Some DB connection objects implement __exit__ on their context
                # manager; FakeConn used in tests may not have it so guard the call.
                if hasattr(conn, "__exit__"):
                    conn.__exit__(None, None, None)
            except Exception:
                # Best-effort: do not let connection cleanup errors affect flow
                pass


@login_required
def trade_agreements():
    """View all trade agreements for current user."""
    user_id = session["user_id"]

    with get_db_connection() as conn:
        db = conn.cursor()

        # Get agreements where user is proposer or receiver
        db.execute(
            """
            SELECT ta.id, ta.proposer_id, ta.proposer_resource, ta.proposer_amount,
                   ta.receiver_id, ta.receiver_resource, ta.receiver_amount,
                   ta.interval_hours, ta.next_execution, ta.last_execution,
                   ta.max_executions, ta.execution_count, ta.status,
                   ta.created_at, ta.message,
                   p.username as proposer_name, r.username as receiver_name
            FROM trade_agreements ta
            JOIN users p ON ta.proposer_id = p.id
            JOIN users r ON ta.receiver_id = r.id
            WHERE (ta.proposer_id = %s OR ta.receiver_id = %s)
              AND ta.status != 'cancelled'
            ORDER BY
                CASE ta.status
                    WHEN 'pending' THEN 1
                    WHEN 'active' THEN 2
                    WHEN 'paused' THEN 3
                    ELSE 4
                END,
                ta.created_at DESC
        """,
            (user_id, user_id),
        )

        agreements = db.fetchall()

        # Get list of all users for the proposal dropdown
        db.execute(
            """
            SELECT id, username FROM users
            WHERE id != %s
            ORDER BY username
        """,
            (user_id,),
        )
        users = db.fetchall()

    # Resources that can be traded
    tradeable_resources = ["money"] + variables.RESOURCES

    return render_template(
        "trade_agreements.html",
        agreements=agreements,
        users=users,
        resources=tradeable_resources,
        intervals=VALID_INTERVALS,
        user_id=user_id,
    )


@login_required
def create_trade_agreement():
    """Create a new trade agreement proposal."""
    user_id = session["user_id"]

    # Get form data
    receiver_id = request.form.get("receiver_id")
    proposer_resource = request.form.get("proposer_resource")
    proposer_amount = request.form.get("proposer_amount")
    receiver_resource = request.form.get("receiver_resource")
    receiver_amount = request.form.get("receiver_amount")
    interval_hours = request.form.get("interval_hours")
    max_executions = request.form.get("max_executions")
    message = request.form.get("message", "")

    # Validation
    if not all(
        [
            receiver_id,
            proposer_resource,
            proposer_amount,
            receiver_resource,
            receiver_amount,
            interval_hours,
        ]
    ):
        flash("All fields are required", "error")
        return redirect("/trade-agreements")

    try:
        receiver_id = int(receiver_id)
        proposer_amount = int(proposer_amount)
        receiver_amount = int(receiver_amount)
        interval_hours = int(interval_hours)
        max_executions = int(max_executions) if max_executions else None
    except ValueError:
        flash("Invalid numeric values", "error")
        return redirect("/trade-agreements")

    if receiver_id == user_id:
        flash("You cannot create a trade agreement with yourself", "error")
        return redirect("/trade-agreements")

    if proposer_amount < 1 or receiver_amount < 1:
        flash("Amounts must be at least 1", "error")
        return redirect("/trade-agreements")

    if interval_hours not in VALID_INTERVALS:
        flash("Invalid interval selected", "error")
        return redirect("/trade-agreements")

    if max_executions is not None and max_executions < 1:
        flash("Max executions must be at least 1", "error")
        return redirect("/trade-agreements")

    # Validate resources
    valid_resources = ["money"] + variables.RESOURCES
    if (
        proposer_resource not in valid_resources
        or receiver_resource not in valid_resources
    ):
        flash("Invalid resource selected", "error")
        return redirect("/trade-agreements")

    with get_db_connection() as conn:
        db = conn.cursor()

        # Verify receiver exists
        db.execute("SELECT id FROM users WHERE id = %s", (receiver_id,))
        if not db.fetchone():
            flash("Receiver not found", "error")
            return redirect("/trade-agreements")

        # Check proposer has enough resources for at least one execution
        has_enough, balance = check_resource_balance(
            db, user_id, proposer_resource, proposer_amount
        )
        if not has_enough:
            msg = (
                f"You don't have enough {proposer_resource} "
                f"(have {balance:,}, need {proposer_amount:,})"
            )
            flash(msg, "error")
            return redirect("/trade-agreements")

        # Create the agreement
        db.execute(
            """
            INSERT INTO trade_agreements
            (proposer_id, proposer_resource, proposer_amount,
             receiver_id, receiver_resource, receiver_amount,
             interval_hours, max_executions, message, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
            RETURNING id
        """,
            (
                user_id,
                proposer_resource,
                proposer_amount,
                receiver_id,
                receiver_resource,
                receiver_amount,
                interval_hours,
                max_executions,
                message,
            ),
        )

        # Get the new agreement ID (not used, but commit needed)
        db.fetchone()
        conn.commit()

    flash("Trade agreement proposal sent!", "success")
    return redirect("/trade-agreements")


@login_required
def accept_trade_agreement(agreement_id):
    """Accept a pending trade agreement."""
    user_id = session["user_id"]

    with get_db_connection() as conn:
        db = conn.cursor()

        # Get agreement
        db.execute(
            """
            SELECT receiver_id, receiver_resource, receiver_amount, status
            FROM trade_agreements
            WHERE id = %s
        """,
            (agreement_id,),
        )

        row = db.fetchone()
        if not row:
            flash("Agreement not found", "error")
            return redirect("/trade-agreements")

        receiver_id, receiver_resource, receiver_amount, status = row

        if receiver_id != user_id:
            flash("You can only accept agreements sent to you", "error")
            return redirect("/trade-agreements")

        if status != "pending":
            flash("This agreement is no longer pending", "error")
            return redirect("/trade-agreements")

        # Check receiver has enough resources
        has_enough, balance = check_resource_balance(
            db, user_id, receiver_resource, receiver_amount
        )
        if not has_enough:
            msg = (
                f"You don't have enough {receiver_resource} "
                f"(have {balance:,}, need {receiver_amount:,})"
            )
            flash(msg, "error")
            return redirect("/trade-agreements")

        # Activate the agreement and set first execution time
        db.execute(
            """
            UPDATE trade_agreements
            SET status = 'active',
                next_execution = now(),
                updated_at = now()
            WHERE id = %s
        """,
            (agreement_id,),
        )
        conn.commit()

    # Execute the first trade immediately
    success, msg = execute_trade_agreement(agreement_id)

    if success:
        flash("Agreement accepted and first trade executed!", "success")
    else:
        flash(f"Agreement accepted but first trade failed: {msg}", "warning")

    return redirect("/trade-agreements")


@login_required
def reject_trade_agreement(agreement_id):
    """Reject a pending trade agreement."""
    user_id = session["user_id"]

    with get_db_connection() as conn:
        db = conn.cursor()

        db.execute(
            """
            SELECT receiver_id, status FROM trade_agreements WHERE id = %s
        """,
            (agreement_id,),
        )

        row = db.fetchone()
        if not row:
            flash("Agreement not found", "error")
            return redirect("/trade-agreements")

        receiver_id, status = row

        if receiver_id != user_id:
            flash("You can only reject agreements sent to you", "error")
            return redirect("/trade-agreements")

        if status != "pending":
            flash("This agreement is no longer pending", "error")
            return redirect("/trade-agreements")

        db.execute(
            """
            UPDATE trade_agreements
            SET status = 'cancelled', updated_at = now()
            WHERE id = %s
        """,
            (agreement_id,),
        )
        conn.commit()

    flash("Agreement rejected", "success")
    return redirect("/trade-agreements")


@login_required
def cancel_trade_agreement(agreement_id):
    """Cancel an active trade agreement (either party can cancel)."""
    user_id = session["user_id"]

    with get_db_connection() as conn:
        db = conn.cursor()

        db.execute(
            """
            SELECT proposer_id, receiver_id, status FROM trade_agreements WHERE id = %s
        """,
            (agreement_id,),
        )

        row = db.fetchone()
        if not row:
            flash("Agreement not found", "error")
            return redirect("/trade-agreements")

        proposer_id, receiver_id, status = row

        if user_id not in [proposer_id, receiver_id]:
            flash("You are not part of this agreement", "error")
            return redirect("/trade-agreements")

        if status not in ["pending", "active", "paused"]:
            flash("This agreement cannot be cancelled", "error")
            return redirect("/trade-agreements")

        db.execute(
            """
            UPDATE trade_agreements
            SET status = 'cancelled', updated_at = now()
            WHERE id = %s
        """,
            (agreement_id,),
        )
        conn.commit()

    flash("Agreement cancelled", "success")
    return redirect("/trade-agreements")


@login_required
def resume_trade_agreement(agreement_id):
    """Resume a paused trade agreement."""
    user_id = session["user_id"]

    with get_db_connection() as conn:
        db = conn.cursor()

        db.execute(
            """
            SELECT proposer_id, receiver_id, status, interval_hours,
                   proposer_resource, proposer_amount,
                   receiver_resource, receiver_amount
            FROM trade_agreements WHERE id = %s
        """,
            (agreement_id,),
        )

        row = db.fetchone()
        if not row:
            flash("Agreement not found", "error")
            return redirect("/trade-agreements")

        (
            proposer_id,
            receiver_id,
            status,
            interval_hours,
            proposer_resource,
            proposer_amount,
            receiver_resource,
            receiver_amount,
        ) = row

        if user_id not in [proposer_id, receiver_id]:
            flash("You are not part of this agreement", "error")
            return redirect("/trade-agreements")

        if status != "paused":
            flash("This agreement is not paused", "error")
            return redirect("/trade-agreements")

        # Check both parties have enough resources
        has_enough, balance = check_resource_balance(
            db, proposer_id, proposer_resource, proposer_amount
        )
        if not has_enough:
            flash(f"Proposer doesn't have enough {proposer_resource}", "error")
            return redirect("/trade-agreements")

        has_enough, balance = check_resource_balance(
            db, receiver_id, receiver_resource, receiver_amount
        )
        if not has_enough:
            flash(f"Receiver doesn't have enough {receiver_resource}", "error")
            return redirect("/trade-agreements")

        # Resume and schedule next execution
        next_exec = datetime.utcnow() + timedelta(hours=interval_hours)
        db.execute(
            """
            UPDATE trade_agreements
            SET status = 'active', next_execution = %s, updated_at = now()
            WHERE id = %s
        """,
            (next_exec, agreement_id),
        )
        conn.commit()

    flash("Agreement resumed", "success")
    return redirect("/trade-agreements")


def register_trade_agreement_routes(app):
    """Register trade agreement routes with the Flask app."""
    app.add_url_rule("/trade-agreements", "trade_agreements", trade_agreements)
    app.add_url_rule(
        "/trade-agreements/create",
        "create_trade_agreement",
        create_trade_agreement,
        methods=["POST"],
    )
    app.add_url_rule(
        "/trade-agreements/<int:agreement_id>/accept",
        "accept_trade_agreement",
        accept_trade_agreement,
        methods=["POST"],
    )
    app.add_url_rule(
        "/trade-agreements/<int:agreement_id>/reject",
        "reject_trade_agreement",
        reject_trade_agreement,
        methods=["POST"],
    )
    app.add_url_rule(
        "/trade-agreements/<int:agreement_id>/cancel",
        "cancel_trade_agreement",
        cancel_trade_agreement,
        methods=["POST"],
    )
    app.add_url_rule(
        "/trade-agreements/<int:agreement_id>/resume",
        "resume_trade_agreement",
        resume_trade_agreement,
        methods=["POST"],
    )
