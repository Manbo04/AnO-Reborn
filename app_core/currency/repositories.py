from decimal import Decimal


def get_gold_and_currency(db, user_id):
    """Returns (gold, currency_balance) as floats."""
    db.execute(
        "SELECT gold, national_currency_balance FROM stats WHERE id = %s",
        (user_id,),
    )
    row = db.fetchone()
    if not row:
        return 0.0, 0.0
    gold = float(row[0]) if row[0] is not None else 0.0
    currency = float(row[1]) if row[1] is not None else 0.0
    return gold, currency


def debit_gold(db, user_id, amount):
    db.execute(
        "UPDATE stats SET gold = GREATEST(0, gold - %s) WHERE id = %s",
        (amount, user_id),
    )


def credit_gold(db, user_id, amount):
    db.execute("UPDATE stats SET gold = gold + %s WHERE id = %s", (amount, user_id))


def debit_currency(db, user_id, amount):
    db.execute(
        """
        UPDATE stats
        SET national_currency_balance = GREATEST(0, national_currency_balance - %s)
        WHERE id = %s
        """,
        (amount, user_id),
    )


def credit_currency(db, user_id, amount):
    db.execute(
        "UPDATE stats SET national_currency_balance = national_currency_balance + %s WHERE id = %s",
        (amount, user_id),
    )


def log_conversion(db, user_id, direction, gold_amount, currency_amount, rate):
    db.execute(
        """
        INSERT INTO national_currency_conversions
            (user_id, direction, gold_amount, currency_amount, rate)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (user_id, direction, gold_amount, currency_amount, rate),
    )


def get_conversion_history(db, user_id, limit=10):
    db.execute(
        """
        SELECT direction, gold_amount, currency_amount, rate, created_at
        FROM national_currency_conversions
        WHERE user_id = %s
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (user_id, limit),
    )
    return db.fetchall()


# ---------------------------------------------------------------------------
# Holdings of any nation's currency (migration 0091). The issuer's own
# balance stays in stats.national_currency_balance (the only balance that can
# be redeemed for gold); everyone else's lives in currency_holdings. These
# helpers route to the right one so callers never have to care.
# ---------------------------------------------------------------------------

def get_currency_balance(db, user_id, issuer_id):
    """Balance of ``issuer_id``'s currency held by ``user_id`` (Decimal)."""
    if int(user_id) == int(issuer_id):
        db.execute("SELECT national_currency_balance FROM stats WHERE id = %s", (user_id,))
    else:
        db.execute(
            "SELECT amount FROM currency_holdings WHERE user_id = %s AND issuer_id = %s",
            (user_id, issuer_id),
        )
    row = db.fetchone()
    return Decimal(row[0]) if row and row[0] is not None else Decimal("0")


def take_currency(db, user_id, issuer_id, amount):
    """Atomically debit ``amount`` of ``issuer_id``'s currency from
    ``user_id``. Returns False (and changes nothing) if the balance is short,
    so a concurrent spend can never push it below zero or mint the gap."""
    if int(user_id) == int(issuer_id):
        db.execute(
            """
            UPDATE stats
            SET national_currency_balance = national_currency_balance - %s
            WHERE id = %s AND national_currency_balance >= %s
            RETURNING id
            """,
            (amount, user_id, amount),
        )
    else:
        db.execute(
            """
            UPDATE currency_holdings SET amount = amount - %s
            WHERE user_id = %s AND issuer_id = %s AND amount >= %s
            RETURNING user_id
            """,
            (amount, user_id, issuer_id, amount),
        )
    return db.fetchone() is not None


def give_currency(db, user_id, issuer_id, amount):
    """Credit ``amount`` of ``issuer_id``'s currency to ``user_id``."""
    if int(user_id) == int(issuer_id):
        credit_currency(db, user_id, amount)
        return
    db.execute(
        """
        INSERT INTO currency_holdings (user_id, issuer_id, amount)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id, issuer_id)
        DO UPDATE SET amount = currency_holdings.amount + EXCLUDED.amount
        """,
        (user_id, issuer_id, amount),
    )


def get_user_currency_holdings(db, user_id):
    """Foreign currencies ``user_id`` holds, largest first."""
    db.execute(
        """
        SELECT h.issuer_id, h.amount, u.username, u.currency_name
        FROM currency_holdings h
        JOIN users u ON u.id = h.issuer_id
        WHERE h.user_id = %s AND h.amount > 0
        ORDER BY h.amount DESC
        """,
        (user_id,),
    )
    return [
        {
            "issuer_id": r[0],
            "amount": float(r[1]),
            "issuer_name": r[2],
            "currency_name": currency_label(r[3], r[2]),
        }
        for r in db.fetchall()
    ]


def currency_label(currency_name, username):
    return (currency_name or "").strip() or f"{username} currency"


def get_currency_labels(db, issuer_ids):
    """{issuer id: display name} for the given issuers, one query."""
    ids = sorted({int(i) for i in issuer_ids if i})
    if not ids:
        return {}
    db.execute(
        "SELECT id, username, currency_name FROM users WHERE id = ANY(%s)",
        (ids,),
    )
    return {r[0]: currency_label(r[2], r[1]) for r in db.fetchall()}


def issuer_exists(db, issuer_id):
    db.execute("SELECT 1 FROM users WHERE id = %s", (issuer_id,))
    return db.fetchone() is not None
