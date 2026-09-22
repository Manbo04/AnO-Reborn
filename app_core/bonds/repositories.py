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


def get_outstanding_bond_principal(db, issuer_id):
    """Sum of principal on this issuer's not-yet-resolved bonds (listed or
    active) -- what compute_bond_cap() checks new issuance against, so an
    issuer can't stack unlimited unfunded/active bonds beyond their
    population-scaled capacity."""
    db.execute(
        """
        SELECT COALESCE(SUM(principal), 0) FROM bonds
        WHERE issuer_id = %s AND status IN ('listed', 'active')
        """,
        (issuer_id,),
    )
    row = db.fetchone()
    return float(row[0]) if row and row[0] is not None else 0.0


def get_last_default_resolved_at(db, issuer_id):
    db.execute(
        """
        SELECT resolved_at FROM bonds
        WHERE issuer_id = %s AND status = 'defaulted'
        ORDER BY resolved_at DESC
        LIMIT 1
        """,
        (issuer_id,),
    )
    row = db.fetchone()
    return row[0] if row else None


def insert_bond(db, issuer_id, principal, daily_interest_rate, term_days, auto_escrow):
    db.execute(
        """
        INSERT INTO bonds (issuer_id, principal, daily_interest_rate, term_days, auto_escrow)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
        """,
        (issuer_id, principal, daily_interest_rate, term_days, auto_escrow),
    )
    row = db.fetchone()
    return row[0] if row else None


def get_bond(db, bond_id):
    """Returns the full bond row as a dict-ish tuple, or None."""
    db.execute(
        """
        SELECT id, issuer_id, lender_id, principal, daily_interest_rate, term_days,
               auto_escrow, escrowed_principal, status, default_strikes,
               garnishment_owed, created_at, funded_at, matures_at, resolved_at
        FROM bonds WHERE id = %s
        """,
        (bond_id,),
    )
    return db.fetchone()


def fund_bond(db, bond_id, lender_id, term_days):
    """Atomically claims a listed bond for this lender -- the WHERE
    status='listed' guard means only the first of two concurrent funders
    can ever win; the second gets no row back (see services.fund_bond)."""
    db.execute(
        """
        UPDATE bonds
        SET lender_id = %s, status = 'active', funded_at = NOW(),
            matures_at = NOW() + (%s || ' days')::interval,
            last_tick_at = NOW()
        WHERE id = %s AND status = 'listed'
        RETURNING id
        """,
        (lender_id, term_days, bond_id),
    )
    return db.fetchone()


def cancel_bond(db, bond_id, issuer_id):
    db.execute(
        """
        UPDATE bonds SET status = 'cancelled', resolved_at = NOW()
        WHERE id = %s AND issuer_id = %s AND status = 'listed'
        RETURNING id
        """,
        (bond_id, issuer_id),
    )
    return db.fetchone()


def update_bond_terms(db, bond_id, issuer_id, daily_interest_rate, term_days, auto_escrow):
    """Only listed (unsold) bonds can be edited -- matches Kurai's spec
    ("edited before a Bond is sold")."""
    db.execute(
        """
        UPDATE bonds SET daily_interest_rate = %s, term_days = %s, auto_escrow = %s
        WHERE id = %s AND issuer_id = %s AND status = 'listed'
        RETURNING id
        """,
        (daily_interest_rate, term_days, auto_escrow, bond_id, issuer_id),
    )
    return db.fetchone()


def get_listed_bonds(db, limit=100):
    db.execute(
        """
        SELECT b.id, b.issuer_id, u.username, b.principal, b.daily_interest_rate,
               b.term_days, b.auto_escrow, b.created_at
        FROM bonds b
        JOIN users u ON u.id = b.issuer_id
        WHERE b.status = 'listed'
        ORDER BY b.created_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    return db.fetchall()


def get_bonds_as_issuer(db, user_id, limit=25):
    db.execute(
        """
        SELECT b.id, b.lender_id, u.username, b.principal, b.daily_interest_rate,
               b.term_days, b.auto_escrow, b.escrowed_principal, b.status,
               b.default_strikes, b.garnishment_owed, b.funded_at, b.matures_at
        FROM bonds b
        LEFT JOIN users u ON u.id = b.lender_id
        WHERE b.issuer_id = %s
        ORDER BY b.created_at DESC
        LIMIT %s
        """,
        (user_id, limit),
    )
    return db.fetchall()


def get_bonds_as_lender(db, user_id, limit=25):
    db.execute(
        """
        SELECT b.id, b.issuer_id, u.username, b.principal, b.daily_interest_rate,
               b.term_days, b.escrowed_principal, b.status, b.garnishment_owed,
               b.funded_at, b.matures_at
        FROM bonds b
        JOIN users u ON u.id = b.issuer_id
        WHERE b.lender_id = %s
        ORDER BY b.created_at DESC
        LIMIT %s
        """,
        (user_id, limit),
    )
    return db.fetchall()
