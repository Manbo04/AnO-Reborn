"""SQL for the currency exchange (migration 0091)."""


def get_default_owed(db, issuer_id):
    """Outstanding debt on the issuer's defaulted bonds (0 = not in default).

    A bond stays 'defaulted' forever once it defaults, but the tick keeps
    garnishing garnishment_owed / insurer_owed; once both reach 0 the debt
    is paid off and the currency is no longer capped."""
    db.execute(
        """
        SELECT COALESCE(SUM(garnishment_owed + COALESCE(insurer_owed, 0)), 0)
        FROM bonds
        WHERE issuer_id = %s AND status = 'defaulted'
        """,
        (issuer_id,),
    )
    row = db.fetchone()
    return float(row[0] or 0) if row else 0.0


def insert_offer(db, user_id, issuer_id, type_, amount, price_gold, gold_escrow):
    db.execute(
        """
        INSERT INTO currency_market_offers
            (user_id, issuer_id, type, amount, price_gold, gold_escrow)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING offer_id
        """,
        (user_id, issuer_id, type_, amount, price_gold, gold_escrow),
    )
    return db.fetchone()[0]


def get_offer_owner(db, offer_id):
    """Plain read, used only to learn whose advisory lock to take before
    the real FOR UPDATE read."""
    db.execute("SELECT user_id FROM currency_market_offers WHERE offer_id = %s", (offer_id,))
    row = db.fetchone()
    return row[0] if row else None


def get_offer_for_update(db, offer_id):
    db.execute(
        """
        SELECT user_id, issuer_id, type, amount, price_gold, gold_escrow
        FROM currency_market_offers
        WHERE offer_id = %s
        FOR UPDATE
        """,
        (offer_id,),
    )
    return db.fetchone()


def delete_offer(db, offer_id):
    db.execute("DELETE FROM currency_market_offers WHERE offer_id = %s", (offer_id,))


def update_offer_after_fill(db, offer_id, new_amount, new_escrow):
    db.execute(
        "UPDATE currency_market_offers SET amount = %s, gold_escrow = %s WHERE offer_id = %s",
        (new_amount, new_escrow, offer_id),
    )


def log_trade(db, issuer_id, buyer_id, seller_id, amount, price_gold, gold_total):
    db.execute(
        """
        INSERT INTO currency_market_trades
            (issuer_id, buyer_id, seller_id, amount, price_gold, gold_total)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (issuer_id, buyer_id, seller_id, amount, price_gold, gold_total),
    )


def list_offers(db, issuer_id=None, limit=200):
    params = []
    where = ""
    if issuer_id:
        where = "WHERE o.issuer_id = %s"
        params.append(issuer_id)
    db.execute(
        f"""
        SELECT o.offer_id, o.user_id, u.username, o.issuer_id, i.username,
               i.currency_name, o.type, o.amount, o.price_gold
        FROM currency_market_offers o
        JOIN users u ON u.id = o.user_id
        JOIN users i ON i.id = o.issuer_id
        {where}
        ORDER BY o.type DESC, o.price_gold ASC, o.offer_id ASC
        LIMIT %s
        """,
        tuple(params) + (limit,),
    )
    keys = ("offer_id", "user_id", "username", "issuer_id", "issuer_name",
            "currency_name", "type", "amount", "price_gold")
    return [dict(zip(keys, r)) for r in db.fetchall()]


def list_user_offers(db, user_id):
    db.execute(
        """
        SELECT o.offer_id, o.issuer_id, i.username, i.currency_name, o.type,
               o.amount, o.price_gold, o.gold_escrow
        FROM currency_market_offers o
        JOIN users i ON i.id = o.issuer_id
        WHERE o.user_id = %s
        ORDER BY o.offer_id DESC
        """,
        (user_id,),
    )
    keys = ("offer_id", "issuer_id", "issuer_name", "currency_name", "type",
            "amount", "price_gold", "gold_escrow")
    return [dict(zip(keys, r)) for r in db.fetchall()]


def get_price_summary(db, limit_per_issuer=6):
    """Last price and the recent trades for every currency that has
    traded, newest first: {issuer_id: [(price_gold, amount, created_at), ...]}."""
    db.execute(
        """
        SELECT issuer_id, price_gold, amount, created_at
        FROM (
            SELECT issuer_id, price_gold, amount, created_at,
                   ROW_NUMBER() OVER (PARTITION BY issuer_id ORDER BY id DESC) AS rn
            FROM currency_market_trades
        ) t
        WHERE rn <= %s
        ORDER BY issuer_id, created_at DESC
        """,
        (limit_per_issuer,),
    )
    out = {}
    for issuer_id, price, amount, created_at in db.fetchall():
        out.setdefault(issuer_id, []).append((price, amount, created_at))
    return out


def list_known_currencies(db, user_id):
    """Currencies worth offering in a picker: the user's own, anything they
    hold, and anything with an open offer or a past trade."""
    db.execute(
        """
        SELECT u.id, u.username, u.currency_name
        FROM users u
        WHERE u.id = %s
           OR u.id IN (SELECT issuer_id FROM currency_holdings WHERE user_id = %s AND amount > 0)
           OR u.id IN (SELECT issuer_id FROM currency_market_offers)
           OR u.id IN (SELECT DISTINCT issuer_id FROM currency_market_trades)
           OR u.id IN (SELECT id FROM stats WHERE national_currency_balance > 0)
        ORDER BY u.username
        LIMIT 300
        """,
        (user_id, user_id),
    )
    return db.fetchall()


def get_default_owed_many(db, issuer_ids):
    """{issuer id: owed} for issuers with outstanding defaulted-bond debt."""
    ids = sorted({int(i) for i in issuer_ids})
    if not ids:
        return {}
    db.execute(
        """
        SELECT issuer_id, SUM(garnishment_owed + COALESCE(insurer_owed, 0))
        FROM bonds
        WHERE issuer_id = ANY(%s) AND status = 'defaulted'
        GROUP BY issuer_id
        """,
        (ids,),
    )
    return {r[0]: float(r[1] or 0) for r in db.fetchall() if r[1] and r[1] > 0}
