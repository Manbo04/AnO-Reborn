"""Automatic market orders (Helios, #suggestions "Market UI Rework", 2026-10-03;
schema in migration 0104).

A rule keeps ONE ordinary market offer (offers row, ``market_auto_orders.offer_id``)
topped up once an hour. Up to three limits, all of which must pass (ANDed):

  * reserve_limit -- sell: never let stock fall below it;
                     buy:  stop once stock + what's already on offer reaches it.
  * max_offer     -- never have more than this many units sitting in the offer.
  * max_per_day   -- never add more than this many units in any rolling 24h
                     (market_auto_order_log), so a war that strips the market
                     bare can't drain a stockpile before the owner reacts.

At least one of max_offer / max_per_day is required (DB CHECK too), so a rule
can never post an unbounded amount.

The managed offer is a normal offer: it escrows exactly like /post_offer
(resource for sells, price*amount gold or currency for buys), anyone can fill
it, and cancelling it refunds exactly like /delete_offer. Nothing here moves
money or resources any other way.
"""
from __future__ import annotations

from app_core.currency.repositories import get_currency_balance, give_currency, take_currency

from .repositories import delete_offer, get_user_gold_for_update, get_user_resource_quantity
from .services import give_resource


# ------------------------------------------------------------------ pure
def compute_top_up(kind, stock, on_offer, added_24h, reserve_limit, max_offer,
                   max_per_day, affordable_units=None):
    """How many units to add to the rule's offer this hour -> (units, reason).

    ``kind`` is 'sell' or 'buy'. ``affordable_units`` (buy only) is how many
    more units the owner's funds can escrow at the rule's price. The reason
    names the limit that bound, for the rule's status line.
    """
    stock = max(0, int(stock))
    on_offer = max(0, int(on_offer))
    added_24h = max(0, int(added_24h))

    caps = []  # (headroom, reason if this cap is the one that stops us)
    if max_offer is not None:
        caps.append((max_offer - on_offer, f"Offer is full ({on_offer:,}/{max_offer:,} on the market)"))
    if max_per_day is not None:
        caps.append((max_per_day - added_24h,
                     f"Daily limit reached ({added_24h:,}/{max_per_day:,} added in the last 24h)"))
    if kind == "sell":
        floor = reserve_limit or 0
        caps.append((stock - floor,
                     f"Reserves at minimum ({stock:,} held, keeping {floor:,})" if reserve_limit
                     else "Nothing left to sell"))
    else:
        if reserve_limit is not None:
            caps.append((reserve_limit - stock - on_offer,
                         f"Reserve target reached ({stock:,} held + {on_offer:,} on offer, target {reserve_limit:,})"))
        caps.append((affordable_units if affordable_units is not None else 0,
                     "Not enough funds to back more of this offer"))

    if max_offer is None and max_per_day is None:
        return 0, "Rule needs a maximum offer or a daily limit"
    headroom, reason = min(caps, key=lambda c: c[0])
    units = max(0, int(headroom))
    if units == 0:
        return 0, reason
    return units, f"Added {units:,}"


def describe_rule(kind, resource, price, currency_label, reserve_limit, max_offer, max_per_day):
    """Plain-English one-liner for the rules list (mirrors the form preview)."""
    res = resource.replace("_", " ")
    verb = "Sell" if kind == "sell" else "Buy"
    parts = [f"{verb} {res} at {price:,} {currency_label}"]
    if max_offer is not None:
        parts.append(f"keep up to {max_offer:,} on offer")
    if max_per_day is not None:
        parts.append(f"add at most {max_per_day:,} per 24h")
    if reserve_limit is not None:
        parts.append(
            f"never go below {reserve_limit:,} in reserve" if kind == "sell"
            else f"stop once you hold {reserve_limit:,}"
        )
    return ", ".join(parts) + "."


# --------------------------------------------------------------- escrow
def escrow_for_offer(db, user_id, kind, resource, units, price, currency_id):
    """Take what posting ``units`` more of this offer must lock up, exactly as
    /post_offer does. Returns True, or False if the owner is short (nothing
    is taken in that case: every path is a conditional UPDATE)."""
    if kind == "sell":
        return give_resource(user_id, "bank", resource, units, cursor=db) is True
    cost = int(units) * int(price)
    if currency_id:
        return take_currency(db, user_id, currency_id, cost)
    return give_resource(user_id, "bank", "money", cost, cursor=db) is True


def cancel_offer_with_refund(db, offer_id, user_id):
    """Delete one of ``user_id``'s offers and hand back its escrow, exactly as
    /delete_offer does. Returns the deleted row tuple, or None if it was
    already gone (filled or deleted)."""
    if not offer_id:
        return None
    row = delete_offer(db, offer_id, user_id)
    if not row:
        return None
    offer_type, amount, price, resource, currency_id = row
    if offer_type == "buy" and currency_id:
        give_currency(db, user_id, currency_id, price * amount)
    elif offer_type == "buy":
        give_resource("bank", user_id, "money", price * amount, cursor=db)
    elif offer_type == "sell":
        give_resource("bank", user_id, resource, amount, cursor=db)
    return row


def affordable_units(db, user_id, price, currency_id):
    """Whole units a buy rule can still escrow at ``price``."""
    if currency_id:
        funds = int(get_currency_balance(db, user_id, currency_id))
    else:
        funds = get_user_gold_for_update(db, user_id) or 0
    return max(0, funds // int(price))


# ------------------------------------------------------------ rule CRUD
RULE_COLUMNS = (
    "id, user_id, type, resource, price, currency_id, reserve_limit, max_offer, "
    "max_per_day, alert_pct, active, offer_id, last_run_at, last_status, "
    "last_alert_at, created_at"
)
RULE_KEYS = [c.strip() for c in RULE_COLUMNS.split(",")]


def list_rules(db, user_id):
    """The user's rules plus how much each one's offer currently holds."""
    db.execute(
        f"""
        SELECT {', '.join('r.' + k for k in RULE_KEYS)}, COALESCE(o.amount, 0)
        FROM market_auto_orders r
        LEFT JOIN offers o ON o.offer_id = r.offer_id AND o.user_id = r.user_id
        WHERE r.user_id = %s
        ORDER BY r.active DESC, r.type, r.resource
        """,
        (user_id,),
    )
    rules = []
    for row in db.fetchall():
        rule = dict(zip(RULE_KEYS, row[:-1]))
        rule["on_offer"] = int(row[-1] or 0)
        rules.append(rule)
    return rules


def get_rule(db, rule_id, user_id, for_update=False):
    db.execute(
        f"SELECT {RULE_COLUMNS} FROM market_auto_orders WHERE id=%s AND user_id=%s"
        + (" FOR UPDATE" if for_update else ""),
        (rule_id, user_id),
    )
    row = db.fetchone()
    return dict(zip(RULE_KEYS, row)) if row else None


def save_rule(db, user_id, fields):
    """Create or update the user's rule for (type, resource).

    If an existing rule's price or currency changes, its offer is cancelled
    and refunded first: the escrow was taken at the old terms, and an offer
    can't hold units at two prices. Changing only the limits keeps the offer.
    Returns (rule_id, offer_was_reset).
    """
    # Rule row first, then (inside cancel_offer_with_refund) the offer row:
    # the same rule -> offer -> owner order the hourly tick uses.
    db.execute(
        "SELECT id, price, currency_id, offer_id FROM market_auto_orders "
        "WHERE user_id=%s AND type=%s AND resource=%s FOR UPDATE",
        (user_id, fields["type"], fields["resource"]),
    )
    existing = db.fetchone()
    reset = False
    if existing:
        rule_id, old_price, old_currency, offer_id = existing
        if old_price != fields["price"] or old_currency != fields["currency_id"]:
            cancel_offer_with_refund(db, offer_id, user_id)
            offer_id = None
            reset = True
        db.execute(
            """
            UPDATE market_auto_orders
            SET price=%s, currency_id=%s, reserve_limit=%s, max_offer=%s,
                max_per_day=%s, alert_pct=%s, offer_id=%s, active=TRUE,
                last_status=CASE WHEN %s THEN 'Price changed: old offer refunded' ELSE last_status END
            WHERE id=%s
            """,
            (fields["price"], fields["currency_id"], fields["reserve_limit"],
             fields["max_offer"], fields["max_per_day"], fields["alert_pct"],
             offer_id, reset, rule_id),
        )
        return rule_id, reset
    db.execute(
        """
        INSERT INTO market_auto_orders
            (user_id, type, resource, price, currency_id, reserve_limit,
             max_offer, max_per_day, alert_pct)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (user_id, fields["type"], fields["resource"], fields["price"],
         fields["currency_id"], fields["reserve_limit"], fields["max_offer"],
         fields["max_per_day"], fields["alert_pct"]),
    )
    return db.fetchone()[0], False


def set_rule_active(db, rule_id, user_id, active):
    db.execute(
        "UPDATE market_auto_orders SET active=%s WHERE id=%s AND user_id=%s RETURNING id",
        (bool(active), rule_id, user_id),
    )
    return db.fetchone() is not None


def delete_rule(db, rule_id, user_id):
    """Delete a rule and cancel+refund whatever its offer still holds."""
    rule = get_rule(db, rule_id, user_id, for_update=True)
    if not rule:
        return False
    cancel_offer_with_refund(db, rule["offer_id"], user_id)
    db.execute("DELETE FROM market_auto_orders WHERE id=%s", (rule_id,))
    return True


def stock_of(db, user_id, resource):
    return int(get_user_resource_quantity(db, user_id, resource) or 0)


__all__ = [
    "compute_top_up", "describe_rule", "escrow_for_offer", "cancel_offer_with_refund",
    "affordable_units", "list_rules", "get_rule", "save_rule", "set_rule_active",
    "delete_rule", "stock_of",
]
