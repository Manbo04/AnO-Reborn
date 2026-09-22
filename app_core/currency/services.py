import variables

from .repositories import (
    get_gold_and_currency,
    debit_gold,
    credit_gold,
    debit_currency,
    credit_currency,
    log_conversion,
    get_conversion_history,
)


def get_currency_status(db, user_id):
    """Returns a template-friendly dict describing the nation's central bank
    state: current balances and the fixed rate everyone converts at."""
    gold, currency = get_gold_and_currency(db, user_id)
    return {
        "gold": gold,
        "currency_balance": currency,
        "rate": variables.CURRENCY_GOLD_PER_UNIT,
    }


def _parse_positive_amount(raw):
    try:
        amount = float(raw)
    except (TypeError, ValueError):
        return None
    if amount <= 0:
        return None
    return amount


def mint_currency(db, user_id, units_raw):
    """Converts gold into national currency at the fixed rate. Returns
    (ok, error_message_or_none, flash_category)."""
    # Same advisory-lock convention as app_core/loans/services.py -- without
    # it, two concurrent mint requests both read the same stale gold
    # balance, both pass the "enough gold" check, and both debit it: real
    # gold lost twice for currency minted twice, i.e. a double-mint.
    db.execute("SELECT pg_advisory_xact_lock(%s)", (user_id,))

    units = _parse_positive_amount(units_raw)
    if units is None:
        return False, "Enter a valid amount of currency to mint.", "danger"

    rate = variables.CURRENCY_GOLD_PER_UNIT
    gold_cost = units * rate

    gold, _currency = get_gold_and_currency(db, user_id)
    if gold_cost > gold:
        return False, "You don't have enough gold for that.", "danger"

    debit_gold(db, user_id, gold_cost)
    credit_currency(db, user_id, units)
    log_conversion(db, user_id, "mint", gold_cost, units, rate)
    return True, None, None


def redeem_currency(db, user_id, units_raw):
    """Converts national currency back into gold at the same fixed rate.
    Returns (ok, error_message_or_none, flash_category)."""
    db.execute("SELECT pg_advisory_xact_lock(%s)", (user_id,))

    units = _parse_positive_amount(units_raw)
    if units is None:
        return False, "Enter a valid amount of currency to redeem.", "danger"

    rate = variables.CURRENCY_GOLD_PER_UNIT
    gold_gain = units * rate

    _gold, currency = get_gold_and_currency(db, user_id)
    if units > currency:
        return False, "You don't have that much currency to redeem.", "danger"

    debit_currency(db, user_id, units)
    credit_gold(db, user_id, gold_gain)
    log_conversion(db, user_id, "redeem", gold_gain, units, rate)
    return True, None, None


def fetch_conversion_history(db, user_id):
    return get_conversion_history(db, user_id)
