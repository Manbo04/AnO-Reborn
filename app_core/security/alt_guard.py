"""Multi-account (alt) detection used to block resource funnelling.

Two accounts are "linked" if both have a login_events row from the same IP
within the lookback window. Used to stop one player feeding a main account
through aid, market trades, loans and similar person-to-person transfers.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

LOOKBACK_DAYS = 60
LINKED_MESSAGE = (
    "This action isn't allowed between accounts that share a network/device. "
    "If you live with this player, ask staff to whitelist you."
)


def accounts_linked(db, user_a, user_b) -> bool:
    """True if user_a and user_b share a recent login IP. Fails open on DB error
    (never blocks legit play because of a missing table)."""
    try:
        a, b = int(user_a), int(user_b)
    except (TypeError, ValueError):
        return False
    if a == b:
        return False
    try:
        db.execute("SAVEPOINT alt_guard")
        db.execute(
            """
            SELECT 1
            FROM login_events x
            JOIN login_events y ON x.ip = y.ip
            WHERE x.user_id = %s AND y.user_id = %s
              AND x.ip IS NOT NULL
              AND x.created_at > NOW() - make_interval(days => %s)
              AND y.created_at > NOW() - make_interval(days => %s)
              AND NOT EXISTS (
                  SELECT 1 FROM alt_guard_whitelist w
                  WHERE (w.user_a = LEAST(%s, %s) AND w.user_b = GREATEST(%s, %s))
              )
            LIMIT 1
            """,
            (a, b, LOOKBACK_DAYS, LOOKBACK_DAYS, a, b, a, b),
        )
        hit = db.fetchone() is not None
        db.execute("RELEASE SAVEPOINT alt_guard")
        return hit
    except Exception:
        logger.exception("alt_guard check failed")
        try:
            db.execute("ROLLBACK TO SAVEPOINT alt_guard")
        except Exception:
            pass
        return False


NEW_ACCOUNT_DAYS = 3
NEW_ACCOUNT_MESSAGE = (
    f"Accounts under {NEW_ACCOUNT_DAYS} days old can't send aid yet. "
    "Build up your own nation first."
)


def is_new_account(db, user_id, days: int = NEW_ACCOUNT_DAYS) -> bool:
    """True if the account was created fewer than `days` days ago. The starting
    gold bonus makes fresh accounts the standard funnelling vector, so they
    can't send aid. Fails open on error / unparseable date."""
    try:
        db.execute("SAVEPOINT new_acct_check")
        db.execute(
            "SELECT (NULLIF(date::text, '')::date > CURRENT_DATE - %s) FROM users WHERE id = %s",
            (int(days), int(user_id)),
        )
        row = db.fetchone()
        db.execute("RELEASE SAVEPOINT new_acct_check")
        return bool(row and row[0])
    except Exception:
        logger.exception("new-account check failed")
        try:
            db.execute("ROLLBACK TO SAVEPOINT new_acct_check")
        except Exception:
            pass
        return False


PRICE_SPIKE_FACTOR = 3
NEW_ACCOUNT_UNKNOWN_PRICE_CAP = 50_000_000
PRICE_MESSAGE = (
    "New accounts can't pay far above the going market price. "
    "Check the order book and try a realistic price."
)


def new_account_overpay(db, payer_id, resource, unit_price, amount) -> bool:
    """True if `payer_id` is a new account paying gold well above the median
    open price for `resource` (gold-laundering via a fake buy offer). With no
    price data, caps the total instead. Fails open on error."""
    try:
        if not is_new_account(db, payer_id):
            return False
        db.execute("SAVEPOINT overpay_check")
        db.execute(
            "SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY price) "
            "FROM offers WHERE resource = %s AND currency_id IS NULL",
            (resource,),
        )
        row = db.fetchone()
        db.execute("RELEASE SAVEPOINT overpay_check")
        median = float(row[0]) if row and row[0] is not None else None
        if median:
            return float(unit_price) > median * PRICE_SPIKE_FACTOR
        return int(unit_price) * int(amount) > NEW_ACCOUNT_UNKNOWN_PRICE_CAP
    except Exception:
        logger.exception("overpay check failed")
        try:
            db.execute("ROLLBACK TO SAVEPOINT overpay_check")
        except Exception:
            pass
        return False
