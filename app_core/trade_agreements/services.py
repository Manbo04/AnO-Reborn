import logging
from datetime import datetime, timedelta

from database import get_db_connection, invalidate_user_cache
from .repositories import (
    VALID_INTERVALS,
    TRADE_RESOURCE_LABELS,
    check_resource_balance,
    lock_active_agreement,
    pause_agreement,
    complete_or_reschedule_agreement,
    resolve_trade_partner_id,
    insert_agreement,
    get_agreement_receiver_fields,
    activate_agreement,
    get_agreement_status,
    get_agreement_parties_and_status,
    set_agreement_status,
    get_agreement_resume_fields,
    resume_agreement as repo_resume_agreement,
)

logger = logging.getLogger(__name__)


def execute_trade_agreement(agreement_id, cursor=None):
    """Execute a single trade agreement. Returns (success, message).

    Callable either with an existing request cursor (from a route, inside its
    own transaction) or with no cursor (from the Celery maintenance tick),
    in which case it owns and commits its own connection - same optional-cursor
    convention as app_core.market.services.give_resource.
    """
    owns_connection = cursor is None

    if owns_connection:
        _conn_cm = get_db_connection()
        conn = _conn_cm.__enter__()
        db = conn.cursor()
    else:
        db = cursor
        conn = None
        _conn_cm = None

    try:
        agreement = lock_active_agreement(db, agreement_id)
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

        has_enough, balance = check_resource_balance(
            db, proposer_id, proposer_resource, proposer_amount
        )
        if not has_enough:
            pause_agreement(db, aid)
            if owns_connection:
                conn.commit()
            msg = (
                f"Proposer has insufficient {proposer_resource} "
                f"(has {balance}, needs {proposer_amount})"
            )
            return (False, msg)

        has_enough, balance = check_resource_balance(
            db, receiver_id, receiver_resource, receiver_amount
        )
        if not has_enough:
            pause_agreement(db, aid)
            if owns_connection:
                conn.commit()
            msg = (
                f"Receiver has insufficient {receiver_resource} "
                f"(has {balance}, needs {receiver_amount})"
            )
            return (False, msg)

        # Execute the trade - transfer resources
        from app_core.market import give_resource

        result = give_resource(
            proposer_id, receiver_id, proposer_resource, proposer_amount, cursor=db
        )
        if result is not True:
            return False, f"Failed to transfer {proposer_resource}: {result}"

        result = give_resource(
            receiver_id, proposer_id, receiver_resource, receiver_amount, cursor=db
        )
        if result is not True:
            return False, f"Failed to transfer {receiver_resource}: {result}"

        new_execution_count = execution_count + 1
        next_exec = datetime.utcnow() + timedelta(hours=interval_hours)
        completed = bool(max_executions and new_execution_count >= max_executions)
        complete_or_reschedule_agreement(db, aid, new_execution_count, next_exec, completed)

        if owns_connection:
            conn.commit()

        try:
            invalidate_user_cache(proposer_id)
            invalidate_user_cache(receiver_id)
        except Exception:
            pass

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
        if owns_connection and _conn_cm:
            try:
                _conn_cm.__exit__(None, None, None)
            except Exception:
                # Best-effort: do not let connection cleanup errors affect flow
                pass


def create_agreement(
    db,
    user_id,
    receiver_id_raw,
    receiver_query,
    proposer_resource,
    proposer_amount,
    receiver_resource,
    receiver_amount,
    interval_hours,
    max_executions,
    message,
):
    """Validate and create a new trade agreement proposal. Returns (ok, error_message_or_none)."""
    if not all(
        [
            receiver_id_raw or receiver_query,
            proposer_resource,
            proposer_amount,
            receiver_resource,
            receiver_amount,
            interval_hours,
        ]
    ):
        return False, "All required fields must be filled in"

    try:
        proposer_amount = int(proposer_amount)
        receiver_amount = int(receiver_amount)
        interval_hours = int(interval_hours)
        max_executions = int(max_executions) if max_executions else None
    except ValueError:
        return False, "Invalid numeric values"

    if proposer_amount < 1 or receiver_amount < 1:
        return False, "Amounts must be at least 1"

    if interval_hours not in VALID_INTERVALS:
        return False, "Invalid interval selected"

    if max_executions is not None and max_executions < 1:
        return False, "Max executions must be at least 1"

    if not proposer_resource or not receiver_resource:
        return False, "Invalid resource selected"

    receiver_id = resolve_trade_partner_id(db, user_id, receiver_id_raw, receiver_query)
    if not receiver_id:
        return False, "Trade partner not found. Enter an exact country name or nation ID."

    has_enough, balance = check_resource_balance(db, user_id, proposer_resource, proposer_amount)
    if not has_enough:
        res_label = TRADE_RESOURCE_LABELS.get(proposer_resource, proposer_resource.replace("_", " "))
        return False, (
            f"You don't have enough {res_label} "
            f"(have {balance:,}, need {proposer_amount:,})"
        )

    insert_agreement(
        db,
        user_id,
        proposer_resource,
        proposer_amount,
        receiver_id,
        receiver_resource,
        receiver_amount,
        interval_hours,
        max_executions,
        message,
    )
    return True, None


def accept_agreement(db, agreement_id, user_id):
    """Returns (ok, error_message_or_none). Does not execute the first trade -
    caller runs execute_trade_agreement separately, after this commits."""
    row = get_agreement_receiver_fields(db, agreement_id)
    if not row:
        return False, "Agreement not found"

    receiver_id, receiver_resource, receiver_amount, status = row

    if receiver_id != user_id:
        return False, "You can only accept agreements sent to you"

    if status != "pending":
        return False, "This agreement is no longer pending"

    has_enough, balance = check_resource_balance(db, user_id, receiver_resource, receiver_amount)
    if not has_enough:
        return False, (
            f"You don't have enough {receiver_resource} "
            f"(have {balance:,}, need {receiver_amount:,})"
        )

    activate_agreement(db, agreement_id)
    return True, None


def reject_agreement(db, agreement_id, user_id):
    row = get_agreement_status(db, agreement_id)
    if not row:
        return False, "Agreement not found"

    receiver_id, status = row
    if receiver_id != user_id:
        return False, "You can only reject agreements sent to you"
    if status != "pending":
        return False, "This agreement is no longer pending"

    set_agreement_status(db, agreement_id, "cancelled")
    return True, None


def cancel_agreement(db, agreement_id, user_id):
    row = get_agreement_parties_and_status(db, agreement_id)
    if not row:
        return False, "Agreement not found"

    proposer_id, receiver_id, status = row
    if user_id not in [proposer_id, receiver_id]:
        return False, "You are not part of this agreement"
    if status not in ["pending", "active", "paused"]:
        return False, "This agreement cannot be cancelled"

    set_agreement_status(db, agreement_id, "cancelled")
    return True, None


def resume_agreement(db, agreement_id, user_id):
    row = get_agreement_resume_fields(db, agreement_id)
    if not row:
        return False, "Agreement not found"

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
        return False, "You are not part of this agreement"
    if status != "paused":
        return False, "This agreement is not paused"

    has_enough, _ = check_resource_balance(db, proposer_id, proposer_resource, proposer_amount)
    if not has_enough:
        return False, f"Proposer doesn't have enough {proposer_resource}"

    has_enough, _ = check_resource_balance(db, receiver_id, receiver_resource, receiver_amount)
    if not has_enough:
        return False, f"Receiver doesn't have enough {receiver_resource}"

    next_exec = datetime.utcnow() + timedelta(hours=interval_hours)
    repo_resume_agreement(db, agreement_id, next_exec)
    return True, None
