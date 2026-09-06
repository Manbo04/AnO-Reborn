import variables

from .repositories import (
    get_active_loan,
    get_total_population,
    get_gold,
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


def get_loan_status(db, user_id):
    """Returns a template-friendly dict describing the nation's loan state,
    whether or not it currently has an active loan."""
    loan = get_active_loan(db, user_id)
    cap = compute_loan_cap(db, user_id)
    if not loan:
        return {
            "has_active_loan": False,
            "cap": cap,
            "min_amount": variables.LOAN_MIN_AMOUNT,
            "interest_rate": variables.LOAN_INTEREST_RATE_HOURLY,
        }

    loan_id, principal, balance, interest_rate, taken_at = loan
    return {
        "has_active_loan": True,
        "loan_id": loan_id,
        "principal": float(principal),
        "balance": float(balance),
        "interest_rate": float(interest_rate),
        "taken_at": taken_at,
        "hourly_interest": float(balance) * float(interest_rate),
        "cap": cap,
    }


def take_loan(db, user_id, amount):
    """Returns (ok, error_message_or_none, flash_category)."""
    if get_active_loan(db, user_id):
        return False, "You already have an active loan — repay it before borrowing again.", "warning"

    try:
        amount = int(amount)
    except (TypeError, ValueError):
        return False, "Enter a valid loan amount.", "danger"

    if amount < variables.LOAN_MIN_AMOUNT:
        return False, f"Minimum loan amount is ${variables.LOAN_MIN_AMOUNT:,}.", "danger"

    cap = compute_loan_cap(db, user_id)
    if amount > cap:
        return False, f"That exceeds your borrowing capacity (${cap:,}, based on population).", "danger"

    insert_loan(db, user_id, amount, variables.LOAN_INTEREST_RATE_HOURLY)
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
