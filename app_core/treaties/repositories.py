def get_active_treaties(db, user_id):
    db.execute(
        """
        SELECT t.id, t.treaty_type, t.created_at, u.username as other_nation, u.id as other_id, t.sender_id
        FROM nation_treaties t
        JOIN users u ON (u.id = t.recipient_id AND t.sender_id = %s) OR (u.id = t.sender_id AND t.recipient_id = %s)
        WHERE t.status = 'active' AND (t.sender_id = %s OR t.recipient_id = %s)
        """,
        (user_id, user_id, user_id, user_id),
    )
    return db.fetchall()


def get_incoming_treaties(db, user_id):
    db.execute(
        """
        SELECT t.id, t.treaty_type, t.created_at, u.username as sender_name, u.id as sender_id
        FROM nation_treaties t
        JOIN users u ON u.id = t.sender_id
        WHERE t.status = 'pending' AND t.recipient_id = %s
        """,
        (user_id,),
    )
    return db.fetchall()


def get_outgoing_treaties(db, user_id):
    db.execute(
        """
        SELECT t.id, t.treaty_type, t.created_at, u.username as recipient_name, u.id as recipient_id
        FROM nation_treaties t
        JOIN users u ON u.id = t.recipient_id
        WHERE t.status = 'pending' AND t.sender_id = %s
        """,
        (user_id,),
    )
    return db.fetchall()


def find_user_id_by_username(db, username):
    db.execute("SELECT id FROM users WHERE username = %s", (username,))
    row = db.fetchone()
    return row[0] if row else None


def find_conflicting_treaty(db, treaty_type, sender_id, recipient_id):
    """Any pending/active treaty of this type between the two nations, in either direction."""
    db.execute(
        """
        SELECT id FROM nation_treaties
        WHERE status IN ('pending', 'active') AND treaty_type = %s AND
        ((sender_id = %s AND recipient_id = %s) OR (sender_id = %s AND recipient_id = %s))
        """,
        (treaty_type, sender_id, recipient_id, recipient_id, sender_id),
    )
    return db.fetchone()


def insert_treaty_offer(db, sender_id, recipient_id, treaty_type):
    db.execute(
        """
        INSERT INTO nation_treaties (sender_id, recipient_id, treaty_type, status)
        VALUES (%s, %s, %s, 'pending')
        """,
        (sender_id, recipient_id, treaty_type),
    )


def activate_treaty(db, treaty_id, user_id):
    db.execute(
        "UPDATE nation_treaties SET status = 'active', updated_at = CURRENT_TIMESTAMP "
        "WHERE id = %s AND recipient_id = %s AND status = 'pending'",
        (treaty_id, user_id),
    )


def set_treaty_rejected(db, treaty_id, user_id):
    db.execute(
        "UPDATE nation_treaties SET status = 'rejected', updated_at = CURRENT_TIMESTAMP "
        "WHERE id = %s AND recipient_id = %s AND status = 'pending'",
        (treaty_id, user_id),
    )


def set_treaty_cancelled(db, treaty_id, user_id):
    db.execute(
        "UPDATE nation_treaties SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP "
        "WHERE id = %s AND (sender_id = %s OR recipient_id = %s) AND status IN ('pending', 'active')",
        (treaty_id, user_id, user_id),
    )
