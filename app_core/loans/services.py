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
    get_recent_loans_for_credit,
)


def compute_base_loan_cap(db, user_id):
    """Borrowing capacity before the credit score: scales with the nation's
    own population -- a nation with no provinces has nothing to borrow against."""
    population = get_total_population(db, user_id)
    return int(population * variables.LOAN_CAP_PER_POPULATION)


def _as_utc(ts):
    if ts is None:
        return None
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts


def _classify_loan(principal, status, taken_at, repaid_at, cap_at_take, fallback_cap, now):
    """(outcome, points) for one loan. Pure.

    outcome is one of: on_time, late, defaulted_repaid, current, overdue,
    in_default. There's no forced default for national loans (no interest,
    no deadline enforced by a tick), so "default" is defined by age: a loan
    outstanding past LOAN_DEFAULT_DAYS is in default, past LOAN_TERM_DAYS
    it's overdue.
    """
    term = timedelta(days=variables.LOAN_TERM_DAYS)
    default_after = timedelta(days=variables.LOAN_DEFAULT_DAYS)
    taken_at = _as_utc(taken_at)
    repaid_at = _as_utc(repaid_at)
    if status == "active" or repaid_at is None:
        age = now - taken_at if taken_at else timedelta(0)
        if age > default_after:
            return "in_default", variables.LOAN_CREDIT_IN_DEFAULT_POINTS
        if age > term:
            return "overdue", variables.LOAN_CREDIT_LATE_POINTS
        return "current", 0
    held = repaid_at - taken_at
    if held > default_after:
        return "defaulted_repaid", variables.LOAN_CREDIT_DEFAULT_REPAID_POINTS
    if held > term:
        return "late", variables.LOAN_CREDIT_LATE_POINTS
    # On time. Token loans (tiny vs. the cap at the time) earn only a
    # proportional share, so the score can't be farmed with minimum loans.
    ref_cap = float(cap_at_take) if cap_at_take else float(fallback_cap or 0)
    full_size = ref_cap * variables.LOAN_CREDIT_FULL_SIZE_SHARE
    weight = 1.0 if full_size <= 0 else min(1.0, float(principal) / full_size)
    return "on_time", variables.LOAN_CREDIT_ON_TIME_POINTS * weight


def score_loan_history(loans, fallback_cap, now=None):
    """Pure credit-score calculation over the most recent loans
    [(principal, status, taken_at, repaid_at, cap_at_take)].

    Returns {"points": float in [-MAX, +MAX], "multiplier": 1 + points/100,
    "score": 0-100 display number (50 = neutral), "label", "counts"}.
    """
    now = now or datetime.now(timezone.utc)
    counts = {k: 0 for k in ("on_time", "late", "defaulted_repaid", "current", "overdue", "in_default")}
    points = 0.0
    for principal, status, taken_at, repaid_at, cap_at_take in loans[: variables.LOAN_CREDIT_WINDOW]:
        outcome, pts = _classify_loan(principal, status, taken_at, repaid_at, cap_at_take, fallback_cap, now)
        counts[outcome] += 1
        points += pts
    bound = variables.LOAN_CREDIT_MAX_POINTS
    points = max(-bound, min(bound, points))
    points = round(points, 1)
    score = int(round(50 + 50 * points / bound)) if bound else 50
    if points >= 15:
        label = "Excellent"
    elif points >= 5:
        label = "Good"
    elif points > -5:
        label = "Neutral"
    elif points > -15:
        label = "Poor"
    else:
        label = "Bad"
    return {
        "points": points,
        "multiplier": 1 + points / 100.0,
        "score": score,
        "label": label,
        "counts": counts,
    }


def credit_rules():
    """The rule numbers shown in the page's "How credit works" section."""
    return {
        "term_days": variables.LOAN_TERM_DAYS,
        "default_days": variables.LOAN_DEFAULT_DAYS,
        "window": variables.LOAN_CREDIT_WINDOW,
        "on_time": variables.LOAN_CREDIT_ON_TIME_POINTS,
        "full_share": variables.LOAN_CREDIT_FULL_SIZE_SHARE,
        "late": variables.LOAN_CREDIT_LATE_POINTS,
        "default_repaid": variables.LOAN_CREDIT_DEFAULT_REPAID_POINTS,
        "in_default": variables.LOAN_CREDIT_IN_DEFAULT_POINTS,
        "max": variables.LOAN_CREDIT_MAX_POINTS,
        "threshold": variables.LOAN_HIGH_UTILIZATION_THRESHOLD,
        "base_fee": variables.LOAN_ORIGINATION_FEE,
        "high_fee": variables.LOAN_HIGH_UTILIZATION_FEE,
    }


def get_credit_profile(db, user_id):
    """Base cap, credit score and the resulting effective cap in one place,
    so the page, the quote endpoint and take_loan all agree."""
    base_cap = compute_base_loan_cap(db, user_id)
    loans = get_recent_loans_for_credit(db, user_id, variables.LOAN_CREDIT_WINDOW)
    now = datetime.now(timezone.utc)
    credit = score_loan_history(loans, base_cap, now=now)
    credit["base_cap"] = base_cap
    credit["cap"] = int(base_cap * credit["multiplier"])
    # ieb's indicator: what the cap would be if the open loan were fully
    # repaid right now (repaying on time can lift the score, so it can
    # differ from today's cap). Same scorer, open loan marked repaid now.
    if any(status == "active" for _, status, _, _, _ in loans):
        as_repaid = [
            (p, "repaid", t, now, c) if status == "active" else (p, status, t, r, c)
            for p, status, t, r, c in loans
        ]
        after = score_loan_history(as_repaid, base_cap, now=now)
        credit["cap_if_repaid_now"] = int(base_cap * after["multiplier"])
    else:
        credit["cap_if_repaid_now"] = credit["cap"]
    return credit


def compute_loan_cap(db, user_id):
    """Effective borrowing cap: population-based cap x credit-score multiplier."""
    return get_credit_profile(db, user_id)["cap"]


def compute_fee_rate(amount, cap):
    """One-time origination fee, higher for loans above the
    high-utilization threshold of the borrower's own cap."""
    if cap > 0 and amount > cap * variables.LOAN_HIGH_UTILIZATION_THRESHOLD:
        return variables.LOAN_HIGH_UTILIZATION_FEE
    return variables.LOAN_ORIGINATION_FEE


def loan_quote(amount, cap):
    """What borrowing `amount` against `cap` would cost. Used by take_loan
    itself AND by the live calculator on the loans page (/loans/quote), so
    the page can't drift from what the server actually charges."""
    threshold_value = int(cap * variables.LOAN_HIGH_UTILIZATION_THRESHOLD)
    quote = {
        "amount": amount,
        "cap": cap,
        "threshold": variables.LOAN_HIGH_UTILIZATION_THRESHOLD,
        "threshold_value": threshold_value,
        "min_amount": variables.LOAN_MIN_AMOUNT,
        "valid": False,
        "error": None,
    }
    if amount is None or amount <= 0:
        quote["error"] = "Enter an amount."
        return quote
    fee_rate = compute_fee_rate(amount, cap)
    total = int(round(amount * (1 + fee_rate)))
    quote.update(
        fee_rate=fee_rate,
        fee=total - amount,
        total_repay=total,
        over_threshold=amount > threshold_value,
    )
    if amount < variables.LOAN_MIN_AMOUNT:
        quote["error"] = f"Minimum loan amount is ${variables.LOAN_MIN_AMOUNT:,}."
    elif amount > cap:
        quote["error"] = f"That's over your borrowing capacity (${cap:,})."
    else:
        quote["valid"] = True
    return quote


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
    credit = get_credit_profile(db, user_id)
    cap = credit["cap"]
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
            "credit": credit,
            "threshold_value": int(cap * variables.LOAN_HIGH_UTILIZATION_THRESHOLD),
        }

    loan_id, principal, balance, interest_rate, taken_at = loan
    taken_utc = _as_utc(taken_at) if isinstance(taken_at, datetime) else None
    return {
        "has_active_loan": True,
        "loan_id": loan_id,
        "principal": float(principal),
        "balance": float(balance),
        "fee_charged": float(balance) - float(principal),
        "taken_at": taken_at,
        "cap": cap,
        "credit": credit,
        "threshold_value": int(cap * variables.LOAN_HIGH_UTILIZATION_THRESHOLD),
        # ieb: "a lil indicator for max borrowing capacity when you're
        # already on a loan". One loan at a time, so what's left becomes
        # borrowable only after repaying (plus the cooldown).
        "cap_used_pct": (float(principal) / cap * 100) if cap > 0 else 0,
        "due_at": taken_utc + timedelta(days=variables.LOAN_TERM_DAYS) if taken_utc else None,
        "default_at": taken_utc + timedelta(days=variables.LOAN_DEFAULT_DAYS) if taken_utc else None,
        "cooldown_hours": variables.LOAN_COOLDOWN_HOURS,
        "cap_after_repay": credit.get("cap_if_repaid_now", cap),
    }


def take_loan(db, user_id, amount):
    """Returns (ok, error_message_or_none, flash_category)."""
    # Serializes this user's loan take/repay calls (same pattern as
    # action_loop.py's build_structure and app_core/military/services.py's
    # process_buy_units). Found 2026-09-13: without this, two concurrent
    # take_loan requests both read "no active loan" before either commits,
    # both pass, and both insert_loan()+credit_gold() -- a raced double-take
    # duplicates the loan principal as real, uncapped free gold, with no
    # corresponding second debt properly trackable (get_active_loan only
    # ever returns one row).
    db.execute("SELECT pg_advisory_xact_lock(%s)", (user_id,))

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
        return False, f"That exceeds your borrowing capacity (${cap:,}, based on population and credit score).", "danger"

    balance = loan_quote(amount, cap)["total_repay"]
    insert_loan(db, user_id, amount, balance, cap_at_take=cap)
    credit_gold(db, user_id, amount)
    return True, None, None


def repay_loan(db, user_id, amount):
    """Returns (ok, error_message_or_none, flash_category)."""
    # Same lock as take_loan above. Without it, two concurrent repay
    # requests both read the same stale `balance` and `gold`, both call
    # debit_gold() (real gold lost each time), but both compute
    # `new_balance = balance - amount` from the same stale balance -- the
    # loan's tracked balance only drops once even though the player paid
    # twice.
    db.execute("SELECT pg_advisory_xact_lock(%s)", (user_id,))

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
