def insert_bounty(db, target_id, poster_id, amount):
    db.execute(
        "INSERT INTO bounties (target_id, poster_id, amount) VALUES (%s, %s, %s) "
        "RETURNING id",
        (target_id, poster_id, amount),
    )
    row = db.fetchone()
    return row[0] if row else None


def get_bounty_for_update(db, bounty_id):
    db.execute(
        "SELECT id, target_id, poster_id, amount, status FROM bounties "
        "WHERE id=%s FOR UPDATE",
        (bounty_id,),
    )
    return db.fetchone()


def set_bounty_cancelled(db, bounty_id, poster_id):
    db.execute(
        "UPDATE bounties SET status='cancelled', resolved_at=NOW() "
        "WHERE id=%s AND poster_id=%s AND status='open'",
        (bounty_id, poster_id),
    )
    return db.rowcount > 0


def get_open_bounties_for_target(db, target_id):
    """Row-locks the matching open bounties so a claim can't race a cancel.
    Called from war_orchestrator's independent connection at the moment a war
    concludes - must run inside that same transaction."""
    db.execute(
        "SELECT id, amount, poster_id FROM bounties "
        "WHERE target_id=%s AND status='open' FOR UPDATE",
        (target_id,),
    )
    return db.fetchall()


def mark_bounties_claimed(db, bounty_ids, winner_id):
    if not bounty_ids:
        return
    db.execute(
        "UPDATE bounties SET status='claimed', claimed_by=%s, resolved_at=NOW() "
        "WHERE id = ANY(%s)",
        (winner_id, list(bounty_ids)),
    )


def get_all_open_bounties(db, limit, offset):
    db.execute(
        """
        SELECT b.id, b.amount, b.created_at, ut.username AS target_name, ut.id AS target_id,
               up.username AS poster_name, up.id AS poster_id
        FROM bounties b
        JOIN users ut ON ut.id = b.target_id
        JOIN users up ON up.id = b.poster_id
        WHERE b.status = 'open'
        ORDER BY b.amount DESC, b.id DESC
        LIMIT %s OFFSET %s
        """,
        (limit, offset),
    )
    return db.fetchall()


def count_open_bounties(db):
    db.execute("SELECT COUNT(*) FROM bounties WHERE status='open'")
    row = db.fetchone()
    return row[0] if row else 0


def get_open_bounty_total_for_target(db, target_id):
    db.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM bounties WHERE target_id=%s AND status='open'",
        (target_id,),
    )
    row = db.fetchone()
    return int(row[0]) if row else 0
