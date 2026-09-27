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
