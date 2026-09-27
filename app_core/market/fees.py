"""Trade fees (transport costs) for money trades between nations.

Player suggestion 2026-09-25 (luciuskonst, "Economy tweaks/ideas laundry
list" #5). Whoever completes a trade pays the fee: a buyer pays it on top of
the price, a seller has it taken out of the proceeds. The fee is removed from
the economy (not paid to anyone). Members of the same active currency union
pay the reduced union rate with each other.
"""

import variables


def trade_fee_percent(db, user_a, user_b):
    """Fee percent for a trade between two nations."""
    from app_core.currency_unions.services import share_active_union

    if share_active_union(db, user_a, user_b):
        return variables.UNION_TRADE_FEE_PERCENT
    return variables.TRADE_FEE_PERCENT


def trade_fee(total_price, percent):
    """Fee on a trade total, rounded down (integer gold)."""
    return int(total_price) * int(percent) // 100


def union_partner_ids(db, user_id):
    """Ids of every nation that trades with ``user_id`` at the union rate.

    One query for the whole /market page instead of one
    ``trade_fee_percent`` call per offer row.
    """
    from app_core.currency_unions.services import _safe

    def _read():
        db.execute(
            """
            SELECT b.user_id
            FROM currency_union_members a
            JOIN currency_union_members b ON b.union_id = a.union_id
            WHERE a.user_id = %s AND b.user_id <> a.user_id
              AND (SELECT COUNT(*) FROM currency_union_members c
                    WHERE c.union_id = a.union_id) >= %s
            """,
            (user_id, variables.CURRENCY_UNION_MIN_MEMBERS),
        )
        return {int(row[0]) for row in db.fetchall()}

    return _safe(db, _read, set())


def max_affordable_amount(gold, unit_price, percent):
    """Largest amount a buyer can pay for: amount * price + fee <= gold.

    Mirrors buy_market_offer's check exactly (fee rounded down), so the
    "Max" button on /market never prefills an amount the server rejects.
    """
    gold = int(gold or 0)
    unit_price = int(unit_price or 0)
    if unit_price <= 0 or gold <= 0:
        return 0
    amount = gold * 100 // (unit_price * (100 + int(percent)))

    def _cost(n):
        total = n * unit_price
        return total + trade_fee(total, percent)

    # The fee rounds down, so the estimate can be one or two short.
    while _cost(amount + 1) <= gold:
        amount += 1
    return amount
