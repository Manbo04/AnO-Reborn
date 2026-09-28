"""Per-nation per-tick gold ledger ("revenue history").

The hourly ticks call record_gold_ledger() once per run with every nation's
gold movements for that tick, which writes them in ONE batched INSERT. It is
failure-tolerant by design: it runs inside a SAVEPOINT, so a failed ledger
write rolls back only itself and never the tick's real gold/resource work.

The nation page reads 24h / 7d / 30d totals per category back with
get_ledger_totals() (one indexed query).

Table: nation_revenue_history (migration 0087). amount is signed:
> 0 is income, < 0 is spending.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

RETENTION_DAYS = 30

# category -> player-facing label. Order here is display order.
INCOME_CATEGORIES = {
    "tax": "Taxes",
}
SPENDING_CATEGORIES = {
    "building_upkeep": "Building upkeep",
    "coalition_tax": "Coalition tax",
    "pension_crisis": "Pension crisis",
}

PERIODS = (("24h", "24 hours"), ("7d", "7 days"), ("30d", "30 days"))


def record_gold_ledger(db, rows, prune=False):
    """Write this tick's ledger rows in a single INSERT.

    rows: iterable of (user_id, category, signed_amount). Zero amounts are
    dropped. With prune=True also deletes rows older than RETENTION_DAYS.
    Never raises; returns the number of rows written (0 on failure).
    """
    values = [
        (int(uid), str(cat), int(amount))
        for uid, cat, amount in rows
        if amount and int(amount) != 0
    ]
    if not values and not prune:
        return 0
    try:
        db.execute("SAVEPOINT revenue_history_ledger")
    except Exception as exc:  # cursor without savepoint support
        logger.warning("revenue history: savepoint failed: %s", exc)
        return 0
    try:
        if values:
            from psycopg2.extras import execute_values

            # page_size >= len(values) keeps this to exactly one statement.
            execute_values(
                db,
                "INSERT INTO nation_revenue_history (user_id, category, amount) "
                "VALUES %s",
                values,
                page_size=max(len(values), 1),
            )
        if prune:
            db.execute(
                "DELETE FROM nation_revenue_history "
                "WHERE recorded_at < NOW() - make_interval(days => %s)",
                (RETENTION_DAYS,),
            )
        db.execute("RELEASE SAVEPOINT revenue_history_ledger")
        return len(values)
    except Exception as exc:
        logger.warning("revenue history: ledger write failed: %s", exc)
        try:
            db.execute("ROLLBACK TO SAVEPOINT revenue_history_ledger")
            db.execute("RELEASE SAVEPOINT revenue_history_ledger")
        except Exception:
            pass
        return 0


def get_ledger_totals(db, user_id):
    """24h / 7d / 30d gold totals per category for one nation.

    Returns None when the nation has no ledger rows in the last 30 days,
    else {"rows": [{"label", "kind": "income"|"spending", "24h", "7d",
    "30d"}], "net": {"24h", "7d", "30d"}}. Spending amounts are positive.
    `db` must be a plain (tuple) cursor.
    """
    db.execute(
        """
        SELECT category,
               COALESCE(SUM(amount) FILTER (WHERE recorded_at >= NOW() - INTERVAL '24 hours'), 0),
               COALESCE(SUM(amount) FILTER (WHERE recorded_at >= NOW() - INTERVAL '7 days'), 0),
               COALESCE(SUM(amount), 0)
        FROM nation_revenue_history
        WHERE user_id = %s AND recorded_at >= NOW() - INTERVAL '30 days'
        GROUP BY category
        """,
        (user_id,),
    )
    by_cat = {
        cat: {"24h": int(d24 or 0), "7d": int(d7 or 0), "30d": int(d30 or 0)}
        for cat, d24, d7, d30 in db.fetchall()
    }
    if not by_cat:
        return None

    keys = [k for k, _ in PERIODS]
    ordered = [c for c in INCOME_CATEGORIES if c in by_cat]
    ordered += [c for c in SPENDING_CATEGORIES if c in by_cat]
    ordered += sorted(
        c for c in by_cat if c not in INCOME_CATEGORIES and c not in SPENDING_CATEGORIES
    )

    rows = []
    for cat in ordered:
        vals = by_cat[cat]
        if cat in INCOME_CATEGORIES:
            kind = "income"
        elif cat in SPENDING_CATEGORIES:
            kind = "spending"
        else:
            kind = "income" if vals["30d"] >= 0 else "spending"
        label = (
            INCOME_CATEGORIES.get(cat)
            or SPENDING_CATEGORIES.get(cat)
            or cat.replace("_", " ").capitalize()
        )
        row = {"label": label, "kind": kind}
        for k in keys:
            row[k] = abs(vals[k])
        rows.append(row)

    net = {k: sum(v[k] for v in by_cat.values()) for k in keys}
    return {"rows": rows, "net": net}
