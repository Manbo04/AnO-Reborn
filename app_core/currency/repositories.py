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
