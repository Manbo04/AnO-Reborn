import variables

from app_core.market.repositories import lock_users, get_username, insert_news, user_exists
from app_core.market.services import give_resource

from .repositories import (
    get_total_population,
    get_outstanding_bond_principal,
    get_last_default_resolved_at,
    insert_bond,
    get_bond,
    fund_bond as repo_fund_bond,
    cancel_bond as repo_cancel_bond,
    update_bond_terms,
    get_listed_bonds,
    get_bonds_as_issuer,
    get_bonds_as_lender,
)

# Bond row column indexes (get_bond()) -- named here so callers don't have
# to remember magic indexes into the tuple.
(_ID, _ISSUER, _LENDER, _PRINCIPAL, _RATE, _TERM, _AUTO_ESCROW, _ESCROWED,
 _STATUS, _STRIKES, _GARNISHMENT, _CREATED, _FUNDED, _MATURES, _RESOLVED) = range(15)


def compute_bond_cap(db, user_id):
    """Total (listed+active) bond principal an issuer may have outstanding
    at once, scaled by population -- same shape as loans'
    compute_loan_cap(), kept as an independent cap rather than sharing the
    national loan's, since these are separate systems."""
    population = get_total_population(db, user_id)
    return int(population * variables.BOND_CAP_PER_POPULATION)


def default_cooldown_remaining(db, user_id):
    """Timedelta-free remaining hours (float) of the post-default cooldown,
    or 0 if none/expired. Mirrors loans.services.cooldown_remaining."""
    from datetime import datetime, timedelta, timezone

    last_default = get_last_default_resolved_at(db, user_id)
    if not last_default:
        return 0.0
    elapsed = datetime.now(timezone.utc) - last_default
    remaining = timedelta(days=variables.BOND_DEFAULT_COOLDOWN_DAYS) - elapsed
    return remaining.total_seconds() / 3600 if remaining.total_seconds() > 0 else 0.0


def get_market_status(db, user_id):
    """Template-friendly dict of this player's issuance limits/state, plus
    the open market listing and their own bonds (issued + invested)."""
    cap = compute_bond_cap(db, user_id)
    outstanding = get_outstanding_bond_principal(db, user_id)
    cooldown_hours = default_cooldown_remaining(db, user_id)
    return {
        "cap": cap,
        "outstanding": outstanding,
        "available_to_issue": max(0, cap - outstanding),
        "cooldown_hours_remaining": cooldown_hours,
        "min_principal": variables.BOND_MIN_PRINCIPAL,
        "min_rate": variables.BOND_MIN_INTEREST_RATE,
        "max_rate": variables.BOND_MAX_INTEREST_RATE,
        "min_term": variables.BOND_MIN_TERM_DAYS,
        "max_term": variables.BOND_MAX_TERM_DAYS,
        "listed_bonds": get_listed_bonds(db),
        "my_issued_bonds": get_bonds_as_issuer(db, user_id),
        "my_invested_bonds": get_bonds_as_lender(db, user_id),
    }


def _validate_terms(principal, daily_interest_rate, term_days):
    try:
        principal = int(principal)
        daily_interest_rate = float(daily_interest_rate)
        term_days = int(term_days)
    except (TypeError, ValueError):
        return None, "Enter valid bond terms."

    if principal < variables.BOND_MIN_PRINCIPAL:
        return None, f"Minimum bond principal is ${variables.BOND_MIN_PRINCIPAL:,}."
    if not (variables.BOND_MIN_INTEREST_RATE <= daily_interest_rate <= variables.BOND_MAX_INTEREST_RATE):
        return None, (
            f"Daily interest rate must be between "
            f"{variables.BOND_MIN_INTEREST_RATE * 100:.2f}% and "
            f"{variables.BOND_MAX_INTEREST_RATE * 100:.2f}%."
        )
    if not (variables.BOND_MIN_TERM_DAYS <= term_days <= variables.BOND_MAX_TERM_DAYS):
        return None, (
            f"Term must be between {variables.BOND_MIN_TERM_DAYS} and "
            f"{variables.BOND_MAX_TERM_DAYS} days."
        )
    return (principal, daily_interest_rate, term_days), None


def create_bond(db, issuer_id, principal, daily_interest_rate, term_days, auto_escrow):
    """Returns (ok, error_message_or_none, flash_category)."""
    # Serializes this issuer's bond-creation calls against their own
    # outstanding-cap check -- same advisory-lock pattern as
    # app_core/loans/services.py::take_loan, so two concurrent "create bond"
    # submissions can't both read the same stale outstanding total and both
    # pass a cap check that, taken together, they violate.
    db.execute("SELECT pg_advisory_xact_lock(%s)", (issuer_id,))

    cooldown = default_cooldown_remaining(db, issuer_id)
    if cooldown > 0:
        return False, f"You defaulted on a bond recently — you can issue a new one in {cooldown:.1f}h.", "warning"

    validated, error = _validate_terms(principal, daily_interest_rate, term_days)
    if error:
        return False, error, "danger"
    principal, daily_interest_rate, term_days = validated

    cap = compute_bond_cap(db, issuer_id)
    outstanding = get_outstanding_bond_principal(db, issuer_id)
    if outstanding + principal > cap:
        available = max(0, cap - outstanding)
        return False, (
            f"That exceeds your bond issuance capacity (${available:,} available, "
            f"based on population)."
        ), "danger"

    insert_bond(db, issuer_id, principal, daily_interest_rate, term_days, bool(auto_escrow))
    return True, None, None


def edit_bond(db, bond_id, issuer_id, principal, daily_interest_rate, term_days, auto_escrow):
    """Only unsold (status='listed') bonds can be edited -- Kurai's spec:
    terms are locked once a Bond is sold."""
    bond = get_bond(db, bond_id)
    if not bond or bond[_ISSUER] != issuer_id:
        return False, "Bond not found.", "danger"
    if bond[_STATUS] != "listed":
        return False, "This bond has already been sold and can't be edited.", "warning"

    validated, error = _validate_terms(principal, daily_interest_rate, term_days)
    if error:
        return False, error, "danger"
    principal, daily_interest_rate, term_days = validated

    if principal != float(bond[_PRINCIPAL]):
        # Changing the principal changes the issuer's outstanding exposure,
        # so re-run the same cap check create_bond does (minus this bond's
        # own old amount).
        cap = compute_bond_cap(db, issuer_id)
        outstanding = get_outstanding_bond_principal(db, issuer_id) - float(bond[_PRINCIPAL])
        if outstanding + principal > cap:
            return False, "That principal exceeds your remaining bond issuance capacity.", "danger"

    updated = update_bond_terms(db, bond_id, issuer_id, daily_interest_rate, term_days, bool(auto_escrow))
    if not updated:
        return False, "This bond has already been sold and can't be edited.", "warning"

    # Principal itself is only set at creation (insert_bond); a principal
    # change on an unsold bond is simple enough to be a cancel+recreate
    # from the UI, so it isn't offered as an in-place edit here.
    return True, None, None


def cancel_bond(db, bond_id, issuer_id):
    cancelled = repo_cancel_bond(db, bond_id, issuer_id)
    if not cancelled:
        return False, "That bond can't be cancelled (already sold, or not yours).", "warning"
    return True, None, None


def fund_bond(db, bond_id, lender_id):
    """Lender invests in a listed bond -- returns (ok, error, category).

    Abuse-vector guards:
    -   self-lending: rejected outright (also enforced at the DB level by
        bonds_no_self_lending).
    -   double-spend of the same offer: repositories.fund_bond()'s
        UPDATE ... WHERE status='listed' is the atomicity boundary -- only
        the first of two concurrent funders can ever claim a given bond_id,
        the loser gets no row back and their gold is never touched.
    -   negative-balance underflow: give_resource's conditional
        UPDATE ... WHERE gold>=%s guards the debit; if the lender's gold
        changed between the page load and this submit, it simply fails
        cleanly instead of going negative.
    """
    bond = get_bond(db, bond_id)
    if not bond:
        return False, "Bond not found.", "danger"
    if bond[_STATUS] != "listed":
        return False, "This bond is no longer available.", "warning"

    issuer_id = bond[_ISSUER]
    if issuer_id == lender_id:
        return False, "You can't invest in your own bond.", "danger"

    principal = float(bond[_PRINCIPAL])
    term_days = bond[_TERM]

    # Lock both parties in a fixed (sorted) order, same convention as
    # app_core/market/routes.py's buy/sell offer handlers, so two different
    # trades touching an overlapping pair of users can't deadlock.
    lock_users(db, [issuer_id, lender_id])

    # Re-check status after acquiring the lock -- another concurrent funder
    # may have just won the race while we were waiting on it.
    bond = get_bond(db, bond_id)
    if not bond or bond[_STATUS] != "listed":
        return False, "This bond is no longer available.", "warning"

    claimed = repo_fund_bond(db, bond_id, lender_id, term_days)
    if not claimed:
        return False, "This bond was just funded by someone else.", "warning"

    result = give_resource(lender_id, issuer_id, "gold", int(round(principal)), cursor=db)
    if result is not True:
        from database import rollback_db_cursor
        rollback_db_cursor(db)
        return False, str(result), "danger"

    try:
        issuer_name = get_username(db, issuer_id) or "A nation"
        lender_name = get_username(db, lender_id) or "An investor"
        insert_news(db, issuer_id, f"{lender_name} funded your bond for ${principal:,.0f}.")
        insert_news(db, lender_id, f"You funded {issuer_name}'s bond for ${principal:,.0f}.")
    except Exception:
        pass

    return True, None, None


def fetch_bond_detail(db, bond_id):
    return get_bond(db, bond_id)
