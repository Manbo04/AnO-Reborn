"""Resource offers / direct trades priced in a nation's currency (0091).

``offers.currency_id`` / ``trades.currency_id`` NULL means gold, exactly as
before. When set, every money leg of the trade moves that issuer's currency
instead of gold (escrow, payment, refund); the resource leg never changes.
The normal trade fee (fees.py, incl. the currency-union rate) still applies
and is paid in the same currency: the payer is debited it and nobody is
credited it, so it is burned.
"""

import variables
from app_core.currency.repositories import (
    get_currency_balance,
    get_currency_labels,
    get_user_currency_holdings,
    issuer_exists,
)


def parse_currency_choice(db, raw):
    """Form value -> (issuer_id or None for gold, error message or None)."""
    raw = (raw or "").strip()
    if raw in ("", "gold"):
        return None, None
    if not raw.isdigit():
        return None, "Unknown currency."
    issuer_id = int(raw)
    if not issuer_exists(db, issuer_id):
        return None, "That currency doesn't exist."
    return issuer_id, None


def currency_balances(db, user_id):
    """{issuer id: whole units held} for the market's Max buttons."""
    out = {h["issuer_id"]: int(h["amount"]) for h in get_user_currency_holdings(db, user_id)}
    out[int(user_id)] = int(get_currency_balance(db, user_id, user_id))
    return out


# Order-book colour tags (Market UI Rework, 2026-10-03): can the viewer
# actually pay/receive the currency an offer is priced in?
TAG_LABELS = {
    "gold": "Priced in gold",
    "held": "Priced in a currency you hold",
    "exchange": "Priced in a currency you can buy on the Currency Exchange",
    "unavailable": "Priced in a currency you can't get right now",
}
TAG_SHORT = {"gold": "Gold", "held": "Held", "exchange": "Exchange", "unavailable": "No access"}


def classify_offer_currency(currency_id, my_id, my_balances, exchange_issuers):
    """'gold' | 'held' | 'exchange' | 'unavailable' for one offer.

    A nation can always mint its own currency from gold, so its own currency
    counts as held even at a zero balance. 'exchange' means someone other
    than the viewer has a sell offer for that currency on /currency_market.
    """
    if not currency_id:
        return "gold"
    if int(currency_id) == int(my_id) or my_balances.get(currency_id, 0) > 0:
        return "held"
    if currency_id in exchange_issuers:
        return "exchange"
    return "unavailable"


def gold_normalised(price, currency_id):
    """Per-unit price in gold, so offers in different currencies compare.
    Uses the fixed mint/redeem rate (variables.CURRENCY_GOLD_PER_UNIT)."""
    if not currency_id:
        return int(price)
    return int(price) * variables.CURRENCY_GOLD_PER_UNIT


__all__ = [
    "parse_currency_choice", "currency_balances", "get_currency_labels",
    "get_currency_balance", "classify_offer_currency", "gold_normalised",
    "TAG_LABELS", "TAG_SHORT",
]
