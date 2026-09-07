def get_active_loan(db, user_id):
    """Returns (id, principal, balance, interest_rate, taken_at) or None."""
    db.execute(
        """
        SELECT id, principal, balance, interest_rate, taken_at
        FROM user_loans
        WHERE user_id = %s AND status = 'active'
        """,
        (user_id,),
    )
    return db.fetchone()


def get_total_population(db, user_id):
    db.execute(
        "SELECT COALESCE(SUM(population), 0) FROM provinces WHERE userId = %s",
        (user_id,),
    )
    row = db.fetchone()
    return int(row[0]) if row and row[0] else 0


def get_gold(db, user_id):
    db.execute("SELECT gold FROM stats WHERE id = %s", (user_id,))
    row = db.fetchone()
    return float(row[0]) if row and row[0] is not None else 0.0


def insert_loan(db, user_id, principal, balance, interest_rate=0):
    db.execute(
        """
        INSERT INTO user_loans (user_id, principal, balance, interest_rate)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (user_id, principal, balance, interest_rate),
    )
    row = db.fetchone()
    return row[0] if row else None


def get_last_repaid_at(db, user_id):
    db.execute(
        """
        SELECT repaid_at FROM user_loans
        WHERE user_id = %s AND status = 'repaid'
        ORDER BY repaid_at DESC
        LIMIT 1
        """,
        (user_id,),
    )
    row = db.fetchone()
    return row[0] if row else None


def credit_gold(db, user_id, amount):
    db.execute("UPDATE stats SET gold = gold + %s WHERE id = %s", (amount, user_id))


def debit_gold(db, user_id, amount):
    db.execute(
        "UPDATE stats SET gold = GREATEST(0, gold - %s) WHERE id = %s",
        (amount, user_id),
    )


def update_loan_balance(db, loan_id, new_balance):
    db.execute(
        "UPDATE user_loans SET balance = %s WHERE id = %s",
        (new_balance, loan_id),
    )


def mark_loan_repaid(db, loan_id):
    db.execute(
        "UPDATE user_loans SET status = 'repaid', balance = 0, repaid_at = NOW() WHERE id = %s",
        (loan_id,),
    )


def get_loan_history(db, user_id, limit=10):
    db.execute(
        """
        SELECT id, principal, balance, interest_rate, status, taken_at, repaid_at
        FROM user_loans
        WHERE user_id = %s
        ORDER BY taken_at DESC
        LIMIT %s
        """,
        (user_id, limit),
    )
    return db.fetchall()
