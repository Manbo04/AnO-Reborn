from database import get_request_cursor, get_db_connection

def is_active_resource(db, resource):
    db.execute(
        """
        SELECT 1
        FROM resource_dictionary
        WHERE name=%s AND is_active=TRUE
        """,
        (resource,),
    )
    return db.fetchone() is not None

def get_user_resource_quantity(db, user_id, resource):
    db.execute(
        """
        SELECT COALESCE(ue.quantity, 0)
        FROM resource_dictionary rd
        LEFT JOIN user_economy ue
            ON ue.resource_id = rd.resource_id AND ue.user_id = %s
        WHERE rd.name=%s AND rd.is_active=TRUE
        """,
        (user_id, resource),
    )
    row = db.fetchone()
    if row is None:
        return None
    return int(row[0] or 0)

def decrement_gold(db, user_id, amount):
    db.execute(
        (
            "UPDATE stats SET gold=gold-%s "
            "WHERE id=%s AND gold>=%s "
            "RETURNING gold"
        ),
        (amount, user_id, amount),
    )
    return db.fetchone() is not None

def increment_gold(db, user_id, amount):
    db.execute(
        ("UPDATE stats SET gold=gold+%s WHERE id=%s RETURNING gold"),
        (amount, user_id),
    )
    return db.fetchone() is not None

def decrement_resource(db, user_id, resource, amount):
    db.execute(
        (
            """
            WITH rid AS (
                SELECT resource_id
                FROM resource_dictionary
                WHERE name=%s
            )
            UPDATE user_economy ue
            SET quantity = ue.quantity - %s
            FROM rid
            WHERE ue.user_id=%s
              AND ue.resource_id = rid.resource_id
              AND ue.quantity >= %s
            RETURNING ue.quantity
            """
        ),
        (resource, amount, user_id, amount),
    )
    return db.fetchone() is not None

def increment_resource(db, user_id, resource, amount):
    db.execute(
        """
        INSERT INTO user_economy (user_id, resource_id, quantity)
        SELECT %s, rd.resource_id, 0
        FROM resource_dictionary rd
        WHERE rd.name=%s
        ON CONFLICT (user_id, resource_id) DO NOTHING
        """,
        (user_id, resource),
    )
    db.execute(
        (
            """
            WITH rid AS (
                SELECT resource_id
                FROM resource_dictionary
                WHERE name=%s
            )
            UPDATE user_economy ue
            SET quantity = ue.quantity + %s
            FROM rid
            WHERE ue.user_id=%s
              AND ue.resource_id = rid.resource_id
            RETURNING ue.quantity
            """
        ),
        (resource, amount, user_id),
    )
    return db.fetchone() is not None

def count_offers(db, filter_resource, offer_type):
    where_conditions = []
    params = []
    if filter_resource is not None:
        where_conditions.append("o.resource = %s")
        params.append(filter_resource)
    if offer_type is not None:
        where_conditions.append("o.type = %s")
        params.append(offer_type)

    where_clause = ""
    if where_conditions:
        where_clause = "WHERE " + " AND ".join(where_conditions)

    count_query = f"SELECT COUNT(*) FROM offers o {where_clause}"
    db.execute(count_query, tuple(params))
    row = db.fetchone()
    return (row[0] or 0) if row else 0

def get_offers(db, filter_resource, offer_type, price_type, limit, offset):
    where_conditions = []
    params = []
    if filter_resource is not None:
        where_conditions.append("o.resource = %s")
        params.append(filter_resource)
    if offer_type is not None:
        where_conditions.append("o.type = %s")
        params.append(offer_type)

    where_clause = ""
    if where_conditions:
        where_clause = "WHERE " + " AND ".join(where_conditions)

    order_dir = "ASC"
    if price_type == "DESC":
        order_dir = "DESC"

    query = f"""
        SELECT o.user_id, o.type, o.resource, o.amount, o.price,
               o.offer_id, u.username
        FROM offers o
        INNER JOIN users u ON o.user_id = u.id
        {where_clause}
        ORDER BY o.price {order_dir}
        LIMIT %s OFFSET %s
    """
    db.execute(query, tuple(params) + (limit, offset))
    return db.fetchall()

def get_offer_by_id(db, offer_id):
    db.execute(
        "SELECT resource, amount, price, user_id FROM offers WHERE offer_id=%s FOR UPDATE",
        (offer_id,),
    )
    return db.fetchone()

def delete_offer(db, offer_id, user_id=None):
    if user_id:
        db.execute(
            "DELETE FROM offers WHERE offer_id=%s AND user_id=%s RETURNING type, amount, price, resource",
            (offer_id, user_id)
        )
        return db.fetchone()
    else:
        db.execute("DELETE FROM offers WHERE offer_id=%s", (offer_id,))
        return True

def update_offer_amount(db, offer_id, new_amount):
    db.execute(
        "UPDATE offers SET amount=%s WHERE offer_id=%s",
        (new_amount, offer_id),
    )

def lock_users(db, user_ids):
    for uid in sorted(user_ids):
        db.execute("SELECT pg_advisory_xact_lock(%s)", (uid,))

def get_user_gold_for_update(db, user_id):
    db.execute("SELECT gold FROM stats WHERE id=%s FOR UPDATE", (user_id,))
    row = db.fetchone()
    return int(row[0] or 0) if row else None

def get_user_gold(db, user_id):
    db.execute("SELECT gold FROM stats WHERE id=%s", (user_id,))
    row = db.fetchone()
    return int(row[0] or 0) if row else None

def insert_offer(db, user_id, type_, resource, amount, price):
    db.execute(
        (
            "INSERT INTO offers (user_id, type, resource, amount, price) "
            "VALUES (%s, %s, %s, %s, %s)"
        ),
        (user_id, type_, resource, int(amount), int(price)),
    )

def insert_trade(db, offerer, type_, resource, amount, price, offeree):
    db.execute(
        (
            "INSERT INTO trades (offerer, type, resource, amount, price, "
            "offeree) "
            "VALUES (%s, %s, %s, %s, %s, %s)"
        ),
        (offerer, type_, resource, amount, price, offeree),
    )

def get_my_trades(db, user_id):
    db.execute(
        (
            "SELECT trades.offer_id, trades.price, trades.resource, "
            "trades.amount, trades.type, trades.offeree, users.username "
            "FROM trades INNER JOIN users ON trades.offeree=users.id "
            "WHERE trades.offerer=%s ORDER BY trades.offer_id ASC"
        ),
        (user_id,),
    )
    outgoing = db.fetchall()

    db.execute(
        (
            "SELECT trades.offer_id, trades.price, trades.resource, "
            "trades.amount, trades.type, trades.offerer, users.username "
            "FROM trades INNER JOIN users ON trades.offerer=users.id "
            "WHERE trades.offeree=%s ORDER BY trades.offer_id ASC"
        ),
        (user_id,),
    )
    incoming = db.fetchall()
    return outgoing, incoming

def get_my_offers(db, user_id):
    db.execute(
        (
            "SELECT offer_id, price, resource, amount, type "
            "FROM offers WHERE user_id=%s ORDER BY offer_id ASC"
        ),
        (user_id,),
    )
    return db.fetchall()

def delete_trade(db, trade_id, user_id):
    db.execute(
        "DELETE FROM trades WHERE offer_id=%s AND (offeree=%s OR offerer=%s) RETURNING type, resource, amount, price, offerer",
        (trade_id, user_id, user_id)
    )
    return db.fetchone()

def delete_trade_by_id(db, trade_id):
    db.execute("DELETE FROM trades WHERE offer_id=%s", (trade_id,))

def try_lock_trade(db, trade_id):
    db.execute("SELECT pg_try_advisory_lock(%s)", (int(trade_id),))
    row = db.fetchone()
    return row and row[0]

def unlock_trade(db, trade_id):
    db.execute("SELECT pg_advisory_unlock(%s)", (int(trade_id),))

def get_trade_by_id(db, trade_id):
    db.execute(
        (
            "SELECT offeree, type, offerer, resource, amount, price "
            "FROM trades WHERE offer_id=%s"
        ),
        (trade_id,),
    )
    return db.fetchone()

def insert_news(db, user_id, message):
    db.execute(
        "INSERT INTO news (destination_id, message) VALUES (%s, %s)",
        (user_id, message),
    )

def get_username(db, user_id):
    db.execute("SELECT username FROM users WHERE id=%s", (user_id,))
    row = db.fetchone()
    return row[0] if row else None

def user_exists(db, user_id):
    db.execute("SELECT id FROM stats WHERE id=%s", (user_id,))
    return db.fetchone() is not None

