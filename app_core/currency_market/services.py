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


PER_SIDE_CHOICES = (25, 50, 100)


def _tag(issuer_id, user_id, held, cap):
    """How the viewer relates to a currency; drives the row colour + chip.
    own: they issued it (and can redeem it for gold), held: they hold some,
    none: they hold none, capped: issuer is in bond default."""
    if cap is not None:
        return "capped"
    if issuer_id == user_id:
        return "own"
    if held > 0:
        return "held"
    return "none"


TAG_TEXT = {
    "own": ("Yours", "Your own currency: you can redeem it for gold at the Central Bank"),
    "held": ("Held", "You hold some of this currency"),
    "none": ("New", "You don't hold any of this currency yet"),
    "capped": ("Default", "The issuer is in bond default, so this currency's price is capped"),
}


def _spark(history, width=96, height=24):
    """SVG polyline points for the recent prices, oldest -> newest."""
    prices = [float(h[0]) for h in reversed(history)]
    if len(prices) < 2:
        return None
    lo, hi = min(prices), max(prices)
    span = (hi - lo) or 1.0
    step = width / (len(prices) - 1)
    return " ".join(
        f"{i * step:.1f},{height - 2 - (p - lo) / span * (height - 4):.1f}"
        for i, p in enumerate(prices)
    )


def get_page_data(db, user_id, issuer_filter=None, per_side=25):
    from app_core.currency.repositories import (
        currency_label,
    )
    from app_core.currency.services import get_currency_status

    if per_side not in PER_SIDE_CHOICES:
        per_side = PER_SIDE_CHOICES[0]

    offers = repo.list_offers(db, None, limit=1000)
    history = repo.get_price_summary(db, limit_per_issuer=20)
    known = repo.list_known_currencies(db, user_id)
    owed = repo.get_default_owed_many(db, [k[0] for k in known] + [o["issuer_id"] for o in offers])
    status = get_currency_status(db, user_id)
    held = {h["issuer_id"]: Decimal(str(h["amount"])) for h in status["foreign_holdings"]}
    held[user_id] = Decimal(str(status["currency_balance"] or 0))
    gold = Decimal(int(status["gold"] or 0))
    rate = Decimal(str(status["rate"]))

    caps = {}
    for iid in {k[0] for k in known} | {o["issuer_id"] for o in offers}:
        caps[iid] = cap_for_owed(owed.get(iid, 0))

    # Best prices per currency, from everyone's offers but the viewer's.
    best_ask, best_bid, ask_count, bid_count = {}, {}, {}, {}
    for o in offers:
        if o["user_id"] == user_id:
            continue
        iid, price = o["issuer_id"], Decimal(o["price_gold"])
        if o["type"] == "sell":
            ask_count[iid] = ask_count.get(iid, 0) + 1
            if iid not in best_ask or price < best_ask[iid]:
                best_ask[iid] = price
        else:
            bid_count[iid] = bid_count.get(iid, 0) + 1
            if iid not in best_bid or price > best_bid[iid]:
                best_bid[iid] = price

    currencies = []
    for issuer_id, username, currency_name in known:
        trades = history.get(issuer_id, [])
        cap = caps.get(issuer_id)
        h = held.get(issuer_id, Decimal(0))
        last = Decimal(trades[0][0]) if trades else None
        prev = Decimal(trades[1][0]) if len(trades) > 1 else None
        change = None
        if last is not None and prev:
            change = float((last - prev) / prev * 100)
        tag = _tag(issuer_id, user_id, h, cap)
        currencies.append({
            "issuer_id": issuer_id,
            "issuer_name": username,
            "label": currency_label(currency_name, username),
            "last_price": last,
            "change": change,
            "history": trades,
            "spark": _spark(trades),
            "cap": cap,
            "held": h,
            "own": issuer_id == user_id,
            "best_ask": best_ask.get(issuer_id),
            "best_bid": best_bid.get(issuer_id),
            "asks": ask_count.get(issuer_id, 0),
            "bids": bid_count.get(issuer_id, 0),
            "tag": tag,
            "tag_short": TAG_TEXT[tag][0],
            "tag_label": TAG_TEXT[tag][1],
        })
    # Busiest currencies first: open offers, then recent trading, then name.
    currencies.sort(key=lambda c: (-(c["asks"] + c["bids"]), -len(c["history"]), c["label"].lower()))

    asks, bids = [], []
    for o in offers:
        o["label"] = currency_label(o["currency_name"], o["issuer_name"])
        if o["user_id"] == user_id:
            continue
        if issuer_filter and o["issuer_id"] != issuer_filter:
            continue
        iid = o["issuer_id"]
        price = Decimal(o["price_gold"])
        amount = Decimal(o["amount"])
        cap = caps.get(iid)
        h = held.get(iid, Decimal(0))
        o["cap_blocked"] = cap is not None and price > cap
        o["tag"] = _tag(iid, user_id, h, cap)
        o["tag_short"], o["tag_label"] = TAG_TEXT[o["tag"]]
        o["total_gold"] = gold_for(amount, price)
        o["vs_mint"] = float((price - rate) / rate * 100) if rate else None
        if o["type"] == "sell":
            affordable = (gold / price).quantize(CENT, rounding=ROUND_DOWN) if price > 0 else Decimal(0)
            o["max_take"] = min(amount, affordable)
            asks.append(o)
        else:
            o["max_take"] = min(amount, h)
            bids.append(o)
    asks.sort(key=lambda o: (Decimal(o["price_gold"]), o["offer_id"]))
    bids.sort(key=lambda o: (-Decimal(o["price_gold"]), o["offer_id"]))

    selected = None
    if issuer_filter:
        selected = next((c for c in currencies if c["issuer_id"] == issuer_filter), None)
    spread = None
    if selected and selected["best_ask"] is not None and selected["best_bid"] is not None:
        spread = selected["best_ask"] - selected["best_bid"]

    my_offers = repo.list_user_offers(db, user_id)
    for o in my_offers:
        o["label"] = currency_label(o["currency_name"], o["issuer_name"])
        o["total_gold"] = gold_for(o["amount"], o["price_gold"])
        cap = caps.get(o["issuer_id"])
        o["cap_blocked"] = cap is not None and Decimal(o["price_gold"]) > cap

    return {
        "asks": asks[:per_side],
        "bids": bids[:per_side],
        "asks_total": len(asks),
        "bids_total": len(bids),
        "per_side": per_side,
        "per_side_choices": PER_SIDE_CHOICES,
        "my_offers": my_offers,
        "currencies": currencies,
        "selected": selected,
        "spread": spread,
        "currency_status": status,
        "issuer_filter": issuer_filter,
    }
