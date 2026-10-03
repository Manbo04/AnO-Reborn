"""Hourly tick for automatic market orders (app_core/market/auto_orders.py,
migration 0104).

Each active rule is handled in its OWN transaction so one bad rule can't roll
back the others:

  1. lock the rule row (FOR UPDATE SKIP LOCKED), then the managed offer row,
     then the owner (the advisory lock the market's buy/sell routes take) --
     the same offer-before-owner order those routes use, so a buyer filling
     the offer mid-tick simply waits for us (or we for them), never deadlocks;
  2. work out how much to add with compute_top_up (all limits ANDed);
  3. escrow exactly like /post_offer and grow the offer (or open a new one if
     the old one was filled or deleted); log the units for the 24h limit;
  4. optionally warn the owner once a day when the market's last traded price
     has moved more than alert_pct away from the rule's price.

Nothing is minted: every unit put on offer comes out of the owner's stock or
treasury, and the offer is an ordinary one that refunds the normal way.
"""
from datetime import datetime, timedelta, timezone

from app_core.game_ticks.common import handle_exception
from app_core.game_ticks.locks import try_pg_advisory_lock

TASK_NAME = "market_auto_orders"
ADVISORY_LOCK_ID = 9021
MAX_RULES_PER_RUN = 2000
ALERT_COOLDOWN = timedelta(hours=24)
MAX_OFFER_AMOUNT = 2_147_483_647


def run_market_auto_orders(now=None):
    """Returns {"topped_up": n, "idle": n, "skipped": n}."""
    from database import get_db_connection

    counts = {"topped_up": 0, "idle": 0, "skipped": 0}
    with get_db_connection() as conn:
        if not try_pg_advisory_lock(conn, ADVISORY_LOCK_ID, TASK_NAME):
            return counts
        db = conn.cursor()
        db.execute(
            "SELECT id FROM market_auto_orders WHERE active ORDER BY id LIMIT %s",
            (MAX_RULES_PER_RUN,),
        )
        rule_ids = [r[0] for r in db.fetchall()]
        conn.commit()

        for rule_id in rule_ids:
            try:
                outcome = _run_one(db, rule_id, now)
                conn.commit()
                counts[outcome] += 1
            except Exception as e:  # one broken rule must not stop the rest
                conn.rollback()
                handle_exception(e, f"{TASK_NAME}#{rule_id}")
    return counts


def _run_one(db, rule_id, now=None):
    from app_core.market.auto_orders import (
        affordable_units, compute_top_up, escrow_for_offer, stock_of,
    )
    from app_core.market.currency_pricing import gold_normalised
    from app_core.market.repositories import (
        get_last_fill_prices, insert_news, is_active_resource, lock_users,
    )

    now = now or datetime.now(timezone.utc)
    db.execute(
        """
        SELECT user_id, type, resource, price, currency_id, reserve_limit,
               max_offer, max_per_day, alert_pct, offer_id, last_alert_at
        FROM market_auto_orders
        WHERE id = %s AND active
        FOR UPDATE SKIP LOCKED
        """,
        (rule_id,),
    )
    row = db.fetchone()
    if not row:
        return "skipped"  # paused/deleted since the list was read, or locked
    (user_id, kind, resource, price, currency_id, reserve_limit, max_offer,
     max_per_day, alert_pct, offer_id, last_alert_at) = row

    def finish(status, new_offer_id, outcome):
        db.execute(
            "UPDATE market_auto_orders SET last_run_at=%s, last_status=%s, offer_id=%s WHERE id=%s",
            (now, status, new_offer_id, rule_id),
        )
        return outcome

    if not is_active_resource(db, resource):
        return finish("Paused: this resource can't be traded right now", offer_id, "skipped")

    db.execute(
        "SELECT 1 FROM assembly_effects WHERE target_nation_id = %s"
        " AND effect_type = 'sanction' AND active = TRUE"
        " AND (expires_at IS NULL OR expires_at > NOW())",
        (user_id,),
    )
    if db.fetchone():
        return finish("Paused: you are under World Assembly sanctions", offer_id, "skipped")

    # Lock order everywhere: rule row -> offer row -> owner (advisory) ->
    # stats rows. /buy_offer and /sell_offer take offer -> owners, so taking
    # the owner lock before the offer row here could deadlock with a fill.
    on_offer = 0
    if offer_id:
        db.execute(
            "SELECT amount FROM offers WHERE offer_id=%s AND user_id=%s AND type=%s "
            "AND resource=%s FOR UPDATE",
            (offer_id, user_id, kind, resource),
        )
        offer_row = db.fetchone()
        if offer_row:
            on_offer = int(offer_row[0])
        else:
            offer_id = None  # fully filled, or the owner deleted it on /my_offers
    lock_users(db, [user_id])

    db.execute(
        "SELECT COALESCE(SUM(units), 0) FROM market_auto_order_log "
        "WHERE auto_order_id=%s AND created_at > %s",
        (rule_id, now - timedelta(hours=24)),
    )
    added_24h = int(db.fetchone()[0])

    stock = stock_of(db, user_id, resource)
    funds_units = affordable_units(db, user_id, price, currency_id) if kind == "buy" else None
    units, status = compute_top_up(
        kind, stock, on_offer, added_24h, reserve_limit, max_offer, max_per_day,
        affordable_units=funds_units,
    )

    # offers.amount is a Postgres INTEGER.
    units = min(units, MAX_OFFER_AMOUNT - on_offer)

    outcome = "idle"
    if units > 0:
        db.execute("SAVEPOINT auto_order_top_up")
        if not escrow_for_offer(db, user_id, kind, resource, units, price, currency_id):
            # Balance moved between the read and the conditional UPDATE.
            db.execute("ROLLBACK TO SAVEPOINT auto_order_top_up")
            status = "Not enough to top up this hour"
        else:
            if offer_id:
                db.execute(
                    "UPDATE offers SET amount = amount + %s WHERE offer_id=%s",
                    (units, offer_id),
                )
            else:
                db.execute(
                    "INSERT INTO offers (user_id, type, resource, amount, price, currency_id) "
                    "VALUES (%s, %s, %s, %s, %s, %s) RETURNING offer_id",
                    (user_id, kind, resource, units, price, currency_id),
                )
                offer_id = db.fetchone()[0]
            db.execute(
                "INSERT INTO market_auto_order_log (auto_order_id, units, created_at) "
                "VALUES (%s, %s, %s)",
                (rule_id, units, now),
            )
            db.execute("RELEASE SAVEPOINT auto_order_top_up")
            outcome = "topped_up"

    if alert_pct and (last_alert_at is None or now - last_alert_at >= ALERT_COOLDOWN):
        last = get_last_fill_prices(db, [resource]).get(resource)
        mine = gold_normalised(price, currency_id)
        if last and mine:
            last_price = last[0]
            moved = abs(last_price - mine) * 100 / mine
            if moved > alert_pct:
                verb = "sell" if kind == "sell" else "buy"
                insert_news(
                    db, user_id,
                    f"Market moved: {resource.replace('_', ' ')} last traded at "
                    f"{last_price:,} gold per unit, {moved:.0f}% away from your "
                    f"auto-{verb} price of {mine:,} gold. Review it on Market > Auto Orders.",
                )
                db.execute(
                    "UPDATE market_auto_orders SET last_alert_at=%s WHERE id=%s",
                    (now, rule_id),
                )

    return finish(status, offer_id, outcome)
