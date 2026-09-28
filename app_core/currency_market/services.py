"""Currency exchange: nations trade each other's currencies for gold.

Rules (Kurai's national-currency follow-up, 2026-09-27):
* Anyone can hold any nation's currency, but only the issuer can redeem it
  for gold at the fixed 5:1 central-bank rate. Foreign holders trade it here
  or spend it on currency-priced resource offers.
* Offers are priced in whole-cent gold per unit. Creating an offer escrows
  what it promises (gold for a buy offer, the currency for a sell offer);
  cancelling refunds whatever is left. Accepting moves value between the two
  nations only -- no gold or currency is ever created here, and there is no
  fee on the exchange itself.
* Gold is a whole number (stats.gold is BIGINT), so a fill of n units at
  price p pays floor(n * p) gold. A buy offer escrows floor(amount * p) and
  tracks what is left in gold_escrow; since floor is superadditive the fills
  can never need more than was escrowed, and whatever is left when the
  offer is filled or cancelled goes back to its maker.
* Debt cap: while the issuer owes money on a defaulted bond, its currency
  can't trade above sell_cap() gold per unit -- 4.0, minus 0.5 per 100k
  gold still owed, never below 1.0. It applies to every trade of that
  currency (buy and sell offers alike, since each trade has a seller), and
  is checked both when an offer is created and when it is accepted, so an
  old offer can't dodge a default that happened after it was listed.
* Locking: the nations' advisory locks first (sorted, same key as the
  market's lock_users and the central bank's mint/redeem), then the offer
  row FOR UPDATE -- the same order the resource market uses.
"""

from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_FLOOR

from app_core.currency.repositories import (
    get_currency_balance,
    give_currency,
    issuer_exists,
    take_currency,
)
from app_core.market.repositories import (
    decrement_gold,
    increment_gold,
    insert_news,
    get_username,
    lock_users,
)

from . import repositories as repo

CENT = Decimal("0.01")
MAX_PRICE_GOLD = Decimal("1000000")
MAX_AMOUNT = Decimal("1000000000")

DEFAULT_CAP_BASE = 4.0
DEFAULT_CAP_STEP = 0.5          # lost per DEFAULT_CAP_STEP_OWED gold still owed
DEFAULT_CAP_STEP_OWED = 100_000
DEFAULT_CAP_FLOOR = 1.0


def _parse_decimal(raw, maximum):
    try:
        value = Decimal(str(raw).replace(",", "").strip()).quantize(CENT, rounding=ROUND_DOWN)
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not value.is_finite() or value <= 0 or value > maximum:
        return None
    return value


def gold_for(units, price_gold):
    """Whole gold paid for ``units`` at ``price_gold`` (rounded down)."""
    return int((Decimal(units) * Decimal(price_gold)).to_integral_value(rounding=ROUND_FLOOR))


def cap_for_owed(owed):
    if owed <= 0:
        return None
    cap = DEFAULT_CAP_BASE - DEFAULT_CAP_STEP * (owed / DEFAULT_CAP_STEP_OWED)
    return Decimal(str(max(DEFAULT_CAP_FLOOR, cap))).quantize(CENT, rounding=ROUND_DOWN)


def sell_cap(db, issuer_id):
    """Max gold per unit this currency may trade at, or None (no cap)."""
    return cap_for_owed(repo.get_default_owed(db, issuer_id))


def create_offer(db, user_id, issuer_id, type_, amount_raw, price_raw):
    """Returns (ok, message, flash_category)."""
    if type_ not in ("buy", "sell"):
        return False, "Pick buy or sell.", "danger"
    amount = _parse_decimal(amount_raw, MAX_AMOUNT)
    price = _parse_decimal(price_raw, MAX_PRICE_GOLD)
    if amount is None or price is None:
        return False, "Enter a valid amount and price.", "danger"
    if not issuer_exists(db, issuer_id):
        return False, "That currency doesn't exist.", "danger"

    cap = sell_cap(db, issuer_id)
    if cap is not None and price > cap:
        return False, (
            f"This nation is in default on its bonds, so its currency can't "
            f"trade above {cap} gold per unit right now."
        ), "danger"

    gold_total = gold_for(amount, price)
    if gold_total < 1:
        return False, "That offer is worth less than 1 gold.", "danger"

    lock_users(db, [user_id])

    # Escrow is the first write; if it fails nothing has changed.
    if type_ == "buy":
        if not decrement_gold(db, user_id, gold_total):
            return False, "You don't have enough gold to back this buy offer.", "danger"
        escrow = gold_total
    else:
        if not take_currency(db, user_id, issuer_id, amount):
            return False, "You don't hold that much of this currency.", "danger"
        escrow = 0

    repo.insert_offer(db, user_id, issuer_id, type_, amount, price, escrow)
    return True, "Offer posted.", "success"


def cancel_offer(db, user_id, offer_id):
    lock_users(db, [user_id])
    row = repo.get_offer_for_update(db, offer_id)
    if not row:
        return False, "Offer not found or already filled.", "danger"
    owner_id, issuer_id, type_, amount, _price, escrow = row
    if owner_id != user_id:
        return False, "That isn't your offer.", "danger"

    repo.delete_offer(db, offer_id)
    if type_ == "buy":
        if escrow:
            increment_gold(db, user_id, int(escrow))
    else:
        give_currency(db, user_id, issuer_id, amount)
    return True, "Offer cancelled and your escrow refunded.", "success"


def accept_offer(db, user_id, offer_id, amount_raw):
    """Fill (part of) someone else's offer. Returns (ok, message, category)."""
    wanted = _parse_decimal(amount_raw, MAX_AMOUNT)
    if wanted is None:
        return False, "Enter a valid amount.", "danger"

    owner_id = repo.get_offer_owner(db, offer_id)
    if owner_id is None:
        return False, "That offer is gone.", "danger"
    if owner_id == user_id:
        return False, "You can't fill your own offer.", "danger"

    lock_users(db, [user_id, owner_id])
    row = repo.get_offer_for_update(db, offer_id)
    if not row or row[0] != owner_id:
        return False, "That offer is gone.", "danger"
    _owner, issuer_id, type_, remaining, price, escrow = row
    remaining = Decimal(remaining)
    price = Decimal(price)
    escrow = int(escrow)

    units = min(wanted, remaining)
    cap = sell_cap(db, issuer_id)
    if cap is not None and price > cap:
        return False, (
            f"The issuer is in bond default, so this currency can't trade above "
            f"{cap} gold per unit. The offer's owner needs to reprice it."
        ), "danger"

    gold = gold_for(units, price)
    if gold < 1:
        return False, "That's worth less than 1 gold; take a bigger amount.", "danger"

    if type_ == "sell":
        # Maker escrowed the currency; the taker pays gold.
        if not decrement_gold(db, user_id, gold):
            return False, "You don't have enough gold.", "danger"
        increment_gold(db, owner_id, gold)
        give_currency(db, user_id, issuer_id, units)
        buyer_id, seller_id = user_id, owner_id
    else:
        # Maker escrowed gold; the taker hands over currency.
        if gold > escrow:
            return False, "This offer can't cover that fill.", "danger"
        if not take_currency(db, user_id, issuer_id, units):
            return False, "You don't hold that much of this currency.", "danger"
        give_currency(db, owner_id, issuer_id, units)
        increment_gold(db, user_id, gold)
        escrow -= gold
        buyer_id, seller_id = owner_id, user_id

    left = remaining - units
    if left <= 0:
        repo.delete_offer(db, offer_id)
        if type_ == "buy" and escrow > 0:
            increment_gold(db, owner_id, escrow)  # rounding leftover back to its maker
    else:
        repo.update_offer_after_fill(db, offer_id, left, escrow)

    repo.log_trade(db, issuer_id, buyer_id, seller_id, units, price, gold)

    try:
        taker = get_username(db, user_id) or "A nation"
        verb = "bought" if type_ == "sell" else "sold you"
        insert_news(
            db, owner_id,
            f"{taker} {verb} {units:,} currency units via your currency market offer "
            f"at {price} gold each ({gold:,} gold).",
        )
    except Exception:
        pass
    return True, f"Trade done: {units:,} units for {gold:,} gold.", "success"


def get_page_data(db, user_id, issuer_filter=None):
    from app_core.currency.repositories import (
        currency_label,
    )
    from app_core.currency.services import get_currency_status

    offers = repo.list_offers(db, issuer_filter)
    history = repo.get_price_summary(db)
    known = repo.list_known_currencies(db, user_id)
    owed = repo.get_default_owed_many(db, [k[0] for k in known])
    status = get_currency_status(db, user_id)
    held = {h["issuer_id"]: h["amount"] for h in status["foreign_holdings"]}
    held[user_id] = status["currency_balance"]

    currencies = []
    caps = {}
    for issuer_id, username, currency_name in known:
        trades = history.get(issuer_id, [])
        cap = cap_for_owed(owed.get(issuer_id, 0))
        caps[issuer_id] = cap
        currencies.append({
            "issuer_id": issuer_id,
            "issuer_name": username,
            "label": currency_label(currency_name, username),
            "last_price": trades[0][0] if trades else None,
            "history": trades,
            "cap": cap,
            "held": held.get(issuer_id, 0),
            "own": issuer_id == user_id,
        })
    for o in offers:
        o["label"] = currency_label(o["currency_name"], o["issuer_name"])
        cap = caps.get(o["issuer_id"])
        o["cap_blocked"] = cap is not None and o["price_gold"] > cap
    my_offers = repo.list_user_offers(db, user_id)
    for o in my_offers:
        o["label"] = currency_label(o["currency_name"], o["issuer_name"])
    return {
        "offers": [o for o in offers if o["user_id"] != user_id],
        "my_offers": my_offers,
        "currencies": currencies,
        "currency_status": status,
        "issuer_filter": issuer_filter,
    }
