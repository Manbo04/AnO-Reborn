from datetime import datetime, timedelta, timezone

import variables

from .repositories import (
    get_active_loan,
    get_total_population,
    get_gold,
    get_last_repaid_at,
    insert_loan,
    credit_gold,
    debit_gold,
    update_loan_balance,
    mark_loan_repaid,
    get_loan_history,
)


def compute_loan_cap(db, user_id):
    """Borrowing capacity scales with the nation's own population -- a
    nation with no provinces yet has no capacity to borrow against."""
    population = get_total_population(db, user_id)
    return int(population * variables.LOAN_CAP_PER_POPULATION)


def compute_fee_rate(amount, cap):
    """One-time origination fee, higher for loans above the
    high-utilization threshold of the borrower's own cap."""
    if cap > 0 and amount > cap * variables.LOAN_HIGH_UTILIZATION_THRESHOLD:
        return variables.LOAN_HIGH_UTILIZATION_FEE
    return variables.LOAN_ORIGINATION_FEE


def cooldown_remaining(db, user_id):
    """Returns a timedelta of cooldown left after the borrower's last fully
    repaid loan, or None if there isn't one / it's expired."""
    last_repaid_at = get_last_repaid_at(db, user_id)
    if not last_repaid_at:
        return None
    elapsed = datetime.now(timezone.utc) - last_repaid_at
    remaining = timedelta(hours=variables.LOAN_COOLDOWN_HOURS) - elapsed
    return remaining if remaining.total_seconds() > 0 else None


def get_loan_status(db, user_id):
    """Returns a template-friendly dict describing the nation's loan state,
    whether or not it currently has an active loan."""
    loan = get_active_loan(db, user_id)
    cap = compute_loan_cap(db, user_id)
    if not loan:
        remaining = cooldown_remaining(db, user_id)
        return {
            "has_active_loan": False,
            "cap": cap,
            "min_amount": variables.LOAN_MIN_AMOUNT,
            "origination_fee": variables.LOAN_ORIGINATION_FEE,
            "high_utilization_fee": variables.LOAN_HIGH_UTILIZATION_FEE,
            "high_utilization_threshold": variables.LOAN_HIGH_UTILIZATION_THRESHOLD,
            "cooldown_hours_remaining": (remaining.total_seconds() / 3600) if remaining else 0,
        }

    loan_id, principal, balance, interest_rate, taken_at = loan
    return {
        "has_active_loan": True,
        "loan_id": loan_id,
        "principal": float(principal),
        "balance": float(balance),
        "fee_charged": float(balance) - float(principal),
        "taken_at": taken_at,
        "cap": cap,
    }


def take_loan(db, user_id, amount):
    """Returns (ok, error_message_or_none, flash_category)."""
    if get_active_loan(db, user_id):
        return False, "You already have an active loan — repay it before borrowing again.", "warning"

    remaining = cooldown_remaining(db, user_id)
    if remaining:
        hours_left = remaining.total_seconds() / 3600
        return False, f"You're on cooldown after your last loan — {hours_left:.1f}h left.", "warning"

    try:
        amount = int(amount)
    except (TypeError, ValueError):
        return False, "Enter a valid loan amount.", "danger"

    if amount < variables.LOAN_MIN_AMOUNT:
        return False, f"Minimum loan amount is ${variables.LOAN_MIN_AMOUNT:,}.", "danger"

    cap = compute_loan_cap(db, user_id)
    if amount > cap:
        return False, f"That exceeds your borrowing capacity (${cap:,}, based on population).", "danger"

    fee_rate = compute_fee_rate(amount, cap)
    balance = int(round(amount * (1 + fee_rate)))
    insert_loan(db, user_id, amount, balance)
    credit_gold(db, user_id, amount)
    return True, None, None


def repay_loan(db, user_id, amount):
    """Returns (ok, error_message_or_none, flash_category)."""
    loan = get_active_loan(db, user_id)
    if not loan:
        return False, "You don't have an active loan.", "warning"

    loan_id, principal, balance, interest_rate, taken_at = loan
    balance = float(balance)

    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return False, "Enter a valid repayment amount.", "danger"

    if amount <= 0:
        return False, "Enter a valid repayment amount.", "danger"

    gold = get_gold(db, user_id)
    if amount > gold:
        return False, "You don't have enough gold to repay that amount.", "danger"

    amount = min(amount, balance)
    debit_gold(db, user_id, amount)
    new_balance = balance - amount
    if new_balance <= 0:
        mark_loan_repaid(db, loan_id)
    else:
        update_loan_balance(db, loan_id, new_balance)

    return True, None, None


def fetch_loan_history(db, user_id):
    return get_loan_history(db, user_id)
