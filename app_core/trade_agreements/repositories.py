import variables

# Valid interval options (in hours)
VALID_INTERVALS = [1, 6, 12, 24, 48, 72, 168]  # 1h, 6h, 12h, 1d, 2d, 3d, 1 week

# Canonical trade resources (stored in DB); aliases normalized on input
VALID_TRADE_RESOURCES = ["money"] + variables.RESOURCES
RESOURCE_ALIASES = {
    "gold": "money",
    "money": "money",
    "consumer goods": "consumer_goods",
    "consumergoods": "consumer_goods",
}
TRADE_RESOURCE_LABELS = {"money": "Gold"}


def normalize_trade_resource(resource):
    """Map UI aliases (e.g. gold) to canonical resource names."""
    if not resource:
        return None
    key = str(resource).strip().lower().replace(" ", "_")
    key = RESOURCE_ALIASES.get(key, key)
    if key in VALID_TRADE_RESOURCES:
        return key
    return None


def get_resource_column(resource):
    """Get the database column name for a resource."""
    if resource == "money":
        return "gold"
    return resource


def resolve_trade_partner_id(db, current_user_id, receiver_id_raw, receiver_query):
    """Resolve partner from hidden id and/or search text (username or nation ID)."""
    if receiver_id_raw:
        try:
            partner_id = int(receiver_id_raw)
        except (TypeError, ValueError):
            return None
        if partner_id == current_user_id:
            return None
        db.execute("SELECT id FROM users WHERE id = %s", (partner_id,))
        return partner_id if db.fetchone() else None

    query = (receiver_query or "").strip()
    if not query:
        return None
    if query.isdigit():
        partner_id = int(query)
        if partner_id == current_user_id:
            return None
        db.execute("SELECT id FROM users WHERE id = %s", (partner_id,))
        return partner_id if db.fetchone() else None

    db.execute(
        "SELECT id FROM users WHERE LOWER(username) = LOWER(%s)",
        (query,),
    )
    row = db.fetchone()
    return row[0] if row else None


def search_partner_by_id(db, user_id, target_id):
    db.execute(
        """
        SELECT id, username FROM users
        WHERE id != %s AND id = %s
        LIMIT 1
        """,
        (user_id, target_id),
    )
    return db.fetchall()


def search_partners_by_prefix(db, user_id, prefix):
    db.execute(
        """
        SELECT id, username FROM users
        WHERE id != %s AND LOWER(username) LIKE LOWER(%s)
        ORDER BY username
        LIMIT 25
        """,
        (user_id, f"{prefix}%"),
    )
    return db.fetchall()


def check_resource_balance(db, user_id, resource, amount):
    """Check if user has enough of a resource. Returns (has_enough, current_balance)."""
    if resource == "money":
        db.execute("SELECT gold FROM stats WHERE id = %s", (user_id,))
    else:
        db.execute(
            """
            SELECT COALESCE(ue.quantity, 0)
            FROM resource_dictionary rd
            LEFT JOIN user_economy ue
                ON ue.resource_id = rd.resource_id AND ue.user_id = %s
            WHERE rd.name = %s
            """,
            (user_id, resource),
        )

    row = db.fetchone()
    if not row:
        return False, 0

    current = int(row[0]) if row[0] else 0
    return current >= amount, current


def get_agreements_for_user(db, user_id):
    db.execute(
        """
        SELECT ta.id, ta.proposer_id, ta.proposer_resource, ta.proposer_amount,
               ta.receiver_id, ta.receiver_resource, ta.receiver_amount,
               ta.interval_hours, ta.next_execution, ta.last_execution,
               ta.max_executions, ta.execution_count, ta.status,
               ta.created_at, ta.message,
               p.username as proposer_name, r.username as receiver_name
        FROM trade_agreements ta
        JOIN users p ON ta.proposer_id = p.id
        JOIN users r ON ta.receiver_id = r.id
        WHERE (ta.proposer_id = %s OR ta.receiver_id = %s)
          AND ta.status != 'cancelled'
        ORDER BY
            CASE ta.status
                WHEN 'pending' THEN 1
                WHEN 'active' THEN 2
                WHEN 'paused' THEN 3
                ELSE 4
            END,
            ta.created_at DESC
        """,
        (user_id, user_id),
    )
    return db.fetchall()


def lock_active_agreement(db, agreement_id):
    """Lock and fetch an active agreement's execution fields. Used by execute_trade_agreement."""
    db.execute(
        """
        SELECT id, proposer_id, proposer_resource, proposer_amount,
               receiver_id, receiver_resource, receiver_amount,
               execution_count, max_executions, interval_hours
        FROM trade_agreements
        WHERE id = %s AND status = 'active'
        FOR UPDATE
        """,
        (agreement_id,),
    )
    return db.fetchone()


def get_agreement_status(db, agreement_id):
    db.execute(
        "SELECT receiver_id, status FROM trade_agreements WHERE id = %s",
        (agreement_id,),
    )
    return db.fetchone()


def get_agreement_receiver_fields(db, agreement_id):
    db.execute(
        """
        SELECT receiver_id, receiver_resource, receiver_amount, status
        FROM trade_agreements
        WHERE id = %s
        """,
        (agreement_id,),
    )
    return db.fetchone()


def get_agreement_parties_and_status(db, agreement_id):
    db.execute(
        "SELECT proposer_id, receiver_id, status FROM trade_agreements WHERE id = %s",
        (agreement_id,),
    )
    return db.fetchone()


def get_agreement_resume_fields(db, agreement_id):
    db.execute(
        """
        SELECT proposer_id, receiver_id, status, interval_hours,
               proposer_resource, proposer_amount,
               receiver_resource, receiver_amount
        FROM trade_agreements WHERE id = %s
        """,
        (agreement_id,),
    )
    return db.fetchone()


def pause_agreement(db, agreement_id):
    db.execute(
        """
        UPDATE trade_agreements
        SET status = 'paused', updated_at = now()
        WHERE id = %s
        """,
        (agreement_id,),
    )


def complete_or_reschedule_agreement(db, agreement_id, new_execution_count, next_execution, completed):
    if completed:
        db.execute(
            """
            UPDATE trade_agreements
            SET execution_count = %s, last_execution = now(),
                next_execution = NULL, status = 'completed', updated_at = now()
            WHERE id = %s
            """,
            (new_execution_count, agreement_id),
        )
    else:
        db.execute(
            """
            UPDATE trade_agreements
            SET execution_count = %s, last_execution = now(),
                next_execution = %s, updated_at = now()
            WHERE id = %s
            """,
            (new_execution_count, next_execution, agreement_id),
        )


def insert_agreement(
    db,
    proposer_id,
    proposer_resource,
    proposer_amount,
    receiver_id,
    receiver_resource,
    receiver_amount,
    interval_hours,
    max_executions,
    message,
):
    db.execute(
        """
        INSERT INTO trade_agreements
        (proposer_id, proposer_resource, proposer_amount,
         receiver_id, receiver_resource, receiver_amount,
         interval_hours, max_executions, message, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
        RETURNING id
        """,
        (
            proposer_id,
            proposer_resource,
            proposer_amount,
            receiver_id,
            receiver_resource,
            receiver_amount,
            interval_hours,
            max_executions,
            message,
        ),
    )
    row = db.fetchone()
    return row[0] if row else None


def activate_agreement(db, agreement_id):
    db.execute(
        """
        UPDATE trade_agreements
        SET status = 'active',
            next_execution = now(),
            updated_at = now()
        WHERE id = %s
        """,
        (agreement_id,),
    )


def set_agreement_status(db, agreement_id, status):
    db.execute(
        """
        UPDATE trade_agreements
        SET status = %s, updated_at = now()
        WHERE id = %s
        """,
        (status, agreement_id),
    )


def resume_agreement(db, agreement_id, next_execution):
    db.execute(
        """
        UPDATE trade_agreements
        SET status = 'active', next_execution = %s, updated_at = now()
        WHERE id = %s
        """,
        (next_execution, agreement_id),
    )
