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


def insert_loan(db, user_id, principal, balance, interest_rate=0, cap_at_take=None):
    """cap_at_take (migration 0086) records the borrowing cap when the loan
    was taken, so the credit score can tell a real loan from a token one.
    Falls back to the pre-0086 insert if the column isn't there yet."""
    if cap_at_take is not None:
        try:
            db.execute("SAVEPOINT loan_insert_cap")
            db.execute(
                """
                INSERT INTO user_loans (user_id, principal, balance, interest_rate, cap_at_take)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (user_id, principal, balance, interest_rate, cap_at_take),
            )
            row = db.fetchone()
            db.execute("RELEASE SAVEPOINT loan_insert_cap")
            return row[0] if row else None
        except Exception:
            db.execute("ROLLBACK TO SAVEPOINT loan_insert_cap")
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


def get_recent_loans_for_credit(db, user_id, limit):
    """[(principal, status, taken_at, repaid_at, cap_at_take)], newest first."""
    try:
        db.execute("SAVEPOINT loan_credit_hist")
        db.execute(
            """
            SELECT principal, status, taken_at, repaid_at, cap_at_take
            FROM user_loans WHERE user_id = %s
            ORDER BY taken_at DESC LIMIT %s
            """,
            (user_id, limit),
        )
        rows = db.fetchall()
        db.execute("RELEASE SAVEPOINT loan_credit_hist")
        return rows
    except Exception:
        # Pre-0086: no cap_at_take column yet.
        db.execute("ROLLBACK TO SAVEPOINT loan_credit_hist")
        db.execute(
            """
            SELECT principal, status, taken_at, repaid_at, NULL
            FROM user_loans WHERE user_id = %s
            ORDER BY taken_at DESC LIMIT %s
            """,
            (user_id, limit),
        )
        return db.fetchall()


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
