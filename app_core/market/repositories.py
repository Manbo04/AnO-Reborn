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

def get_offer_by_id(db, offer_id):
    db.execute(
        "SELECT resource, amount, price, user_id, type, currency_id FROM offers WHERE offer_id=%s FOR UPDATE",
        (offer_id,),
    )
    return db.fetchone()

def delete_offer(db, offer_id, user_id=None):
    if user_id:
        db.execute(
            "DELETE FROM offers WHERE offer_id=%s AND user_id=%s RETURNING type, amount, price, resource, currency_id",
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

def get_user_resource_quantities(db, user_id):
    """{resource name: quantity} for every active resource, one query."""
    db.execute(
        """
        SELECT rd.name, COALESCE(ue.quantity, 0)
        FROM resource_dictionary rd
        LEFT JOIN user_economy ue
            ON ue.resource_id = rd.resource_id AND ue.user_id = %s
        WHERE rd.is_active=TRUE
        """,
        (user_id,),
    )
    return {row[0]: int(row[1] or 0) for row in db.fetchall()}

def get_user_gold_for_update(db, user_id):
    db.execute("SELECT gold FROM stats WHERE id=%s FOR UPDATE", (user_id,))
    row = db.fetchone()
    return int(row[0] or 0) if row else None

def get_user_gold(db, user_id):
    db.execute("SELECT gold FROM stats WHERE id=%s", (user_id,))
    row = db.fetchone()
    return int(row[0] or 0) if row else None

def insert_offer(db, user_id, type_, resource, amount, price, currency_id=None):
    db.execute(
        (
            "INSERT INTO offers (user_id, type, resource, amount, price, currency_id) "
            "VALUES (%s, %s, %s, %s, %s, %s)"
        ),
        (user_id, type_, resource, int(amount), int(price), currency_id),
    )

def insert_trade(db, offerer, type_, resource, amount, price, offeree, currency_id=None):
    db.execute(
        (
            "INSERT INTO trades (offerer, type, resource, amount, price, "
            "offeree, currency_id) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)"
        ),
        (offerer, type_, resource, amount, price, offeree, currency_id),
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

def get_my_currency_ids(db, user_id):
    """Which of the user's market offers / direct trades are priced in a
    nation currency: ({offer_id: issuer_id}, {trade_id: issuer_id}).
    Kept separate from get_my_offers/get_my_trades so the my_offers
    templates' fixed-width tuple unpacking stays unchanged."""
    db.execute(
        "SELECT offer_id, currency_id FROM offers WHERE user_id=%s AND currency_id IS NOT NULL",
        (user_id,),
    )
    offers = {r[0]: r[1] for r in db.fetchall()}
    db.execute(
        "SELECT offer_id, currency_id FROM trades "
        "WHERE (offerer=%s OR offeree=%s) AND currency_id IS NOT NULL",
        (user_id, user_id),
    )
    trades = {r[0]: r[1] for r in db.fetchall()}
    return offers, trades

def delete_trade(db, trade_id, user_id):
    db.execute(
        "DELETE FROM trades WHERE offer_id=%s AND (offeree=%s OR offerer=%s) RETURNING type, resource, amount, price, offerer, currency_id",
        (trade_id, user_id, user_id)
    )
    return db.fetchone()

def refund_trades_offered_to(db, user_id):
    """Delete direct trades other nations offered to ``user_id``, returning
    their escrow (goods for sell offers, gold for buy offers).

    Used when a nation is reset/deleted: its incoming trades used to be
    deleted outright, so the offering nation's escrow vanished.
    """
    from .services import give_resource

    db.execute(
        "DELETE FROM trades WHERE offeree=%s AND offerer<>%s "
        "RETURNING offerer, type, resource, amount, price",
        (user_id, user_id),
    )
    for offerer, type_, resource, amount, price in db.fetchall() or []:
        if type_ == "sell":
            give_resource("bank", offerer, resource, amount, cursor=db)
        elif type_ == "buy":
            give_resource("bank", offerer, "money", int(amount) * int(price), cursor=db)


def delete_trade_by_id(db, trade_id):
    db.execute("DELETE FROM trades WHERE offer_id=%s", (trade_id,))

def try_lock_trade(db, trade_id):
    db.execute("SELECT pg_try_advisory_lock(%s)", (int(trade_id),))
    row = db.fetchone()
    return row and row[0]

def unlock_trade(db, trade_id):
    db.execute("SELECT pg_advisory_unlock(%s)", (int(trade_id),))

def get_trade_by_id(db, trade_id):
    """FIXED 2026-09-23: found live while auditing app_core/market/ during
    the account cross-contamination investigation -- unrelated bug, real
    double-accept race in accept_trade() (see its route in routes.py).
    try_lock_trade()'s pg_try_advisory_lock is SESSION-scoped, released
    immediately by unlock_trade() -- NOT tied to the surrounding
    transaction's commit. A plain (non-locking) SELECT here meant a second
    concurrent accept_trade call could see the trade row as still present
    even after the first call's delete_trade_by_id(), because under READ
    COMMITTED a plain SELECT never waits on another session's uncommitted
    changes -- it just reads the last COMMITTED snapshot, and that DELETE
    doesn't commit until the whole request's transaction ends at teardown,
    well after unlock_trade() already ran. Adding FOR UPDATE makes the
    real Postgres row lock the actual correctness mechanism (the advisory
    lock remains a fast, non-blocking "already busy" UX layer on top): a
    second racer's FOR UPDATE blocks on the first's held lock and, once
    unblocked by the first's commit, re-reads the fresh (deleted) state --
    same idiom get_offer_by_id() in this same file already uses correctly.
    """
    db.execute(
        (
            "SELECT offeree, type, offerer, resource, amount, price, currency_id "
            "FROM trades WHERE offer_id=%s FOR UPDATE"
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

def is_embargoed(db, embargoer_id, embargoed_id):
    db.execute(
        "SELECT 1 FROM market_embargoes WHERE embargoer_id=%s AND embargoed_id=%s",
        (embargoer_id, embargoed_id),
    )
    return db.fetchone() is not None

def add_embargo(db, embargoer_id, embargoed_id):
    db.execute(
        (
            "INSERT INTO market_embargoes (embargoer_id, embargoed_id) "
            "VALUES (%s, %s) ON CONFLICT DO NOTHING"
        ),
        (embargoer_id, embargoed_id),
    )

def remove_embargo(db, embargoer_id, embargoed_id):
    db.execute(
        "DELETE FROM market_embargoes WHERE embargoer_id=%s AND embargoed_id=%s",
        (embargoer_id, embargoed_id),
    )

def list_embargoes(db, embargoer_id):
    db.execute(
        (
            "SELECT me.embargoed_id, u.username FROM market_embargoes me "
            "INNER JOIN users u ON u.id = me.embargoed_id "
            "WHERE me.embargoer_id=%s ORDER BY me.created_at DESC"
        ),
        (embargoer_id,),
    )
    return db.fetchall()



# --- Order book (Market UI Rework, migration 0104) -------------------------

def get_active_resources(db):
    """Names of every tradable resource, in dictionary order."""
    db.execute(
        "SELECT name FROM resource_dictionary WHERE is_active=TRUE ORDER BY resource_id"
    )
    return [row[0] for row in db.fetchall()]

def get_resource_book(db, resource, exclude_user_id):
    """Every open offer for ``resource`` ('all' = every resource) except the
    viewer's own (those live on /my_offers). Sorting is done by the caller on
    the gold-normalised price, which SQL can't see."""
    params = [exclude_user_id]
    resource_clause = ""
    if resource != "all":
        resource_clause = "AND o.resource = %s"
        params.append(resource)
    db.execute(
        f"""
        SELECT o.user_id, o.type, o.resource, o.amount, o.price,
               o.offer_id, u.username, o.currency_id
        FROM offers o
        INNER JOIN users u ON o.user_id = u.id
        WHERE o.user_id <> %s {resource_clause}
        ORDER BY o.offer_id
        LIMIT 3000
        """,
        tuple(params),
    )
    return db.fetchall()

def get_exchange_issuers(db, exclude_user_id):
    """Currencies someone other than the viewer is selling on /currency_market."""
    db.execute(
        "SELECT DISTINCT issuer_id FROM currency_market_offers "
        "WHERE type='sell' AND user_id <> %s",
        (exclude_user_id,),
    )
    return {row[0] for row in db.fetchall()}

def get_embargo_partners(db, user_id):
    """Nations the user embargoes or is embargoed by (either direction),
    including members of coalitions under mutual coalition embargoes."""
    db.execute(
        "SELECT embargoed_id FROM market_embargoes WHERE embargoer_id=%s "
        "UNION SELECT embargoer_id FROM market_embargoes WHERE embargoed_id=%s",
        (user_id, user_id),
    )
    partners = {row[0] for row in db.fetchall()}
    # Members of coalitions under a coalition embargo (either direction).
    partners |= get_coalition_embargo_partners(db, user_id)
    return partners


def get_coalition_embargo_partners(db, user_id):
    """User IDs blocked specifically due to coalition-level embargoes."""
    partners = set()
    try:
        from app_core.coalitions.repositories import (
            _coalition_id_for_user,
            _members_tbl,
            coalition_embargoes_table_exists,
        )
        if coalition_embargoes_table_exists(db):
            user_col = _coalition_id_for_user(db, user_id)
            if user_col:
                db.execute(
                    "SELECT ce.target_coalition_id FROM coalition_embargoes ce WHERE ce.embargoer_coalition_id = %s "
                    "UNION SELECT ce.embargoer_coalition_id FROM coalition_embargoes ce WHERE ce.target_coalition_id = %s",
                    (user_col, user_col),
                )
                col_partners = [r[0] for r in db.fetchall()]
                if col_partners:
                    members_tbl = _members_tbl()
                    db.execute(
                        f"SELECT userid FROM {members_tbl} WHERE colid = ANY(%s)",
                        (col_partners,),
                    )
                    for r in db.fetchall():
                        partners.add(r[0])
    except Exception:
        pass
    return partners


def get_coalition_embargo_block(db, user_a_id, user_b_id):
    """If trade between user_a_id and user_b_id is blocked by a coalition embargo,
    returns a human-readable reason string, else None."""
    if not user_a_id or not user_b_id or user_a_id == user_b_id:
        return None
    try:
        from app_core.coalitions.repositories import (
            _coalition_id_for_user,
            coalition_embargoes_table_exists,
        )
        if not coalition_embargoes_table_exists(db):
            return None
        col_a = _coalition_id_for_user(db, user_a_id)
        col_b = _coalition_id_for_user(db, user_b_id)
        if not col_a or not col_b or col_a == col_b:
            return None

        db.execute(
            "SELECT ce.embargoer_coalition_id, c1.name, ce.target_coalition_id, c2.name "
            "FROM coalition_embargoes ce "
            "JOIN colNames c1 ON c1.id = ce.embargoer_coalition_id "
            "JOIN colNames c2 ON c2.id = ce.target_coalition_id "
            "WHERE (ce.embargoer_coalition_id=%s AND ce.target_coalition_id=%s) "
            "   OR (ce.embargoer_coalition_id=%s AND ce.target_coalition_id=%s)",
            (col_a, col_b, col_b, col_a),
        )
        row = db.fetchone()
        if row:
            embargoer_id, embargoer_name, target_id, target_name = row
            return (
                f"Trade blocked by coalition embargo: "
                f"{embargoer_name} has placed an embargo on {target_name}."
            )
    except Exception:
        return None
    return None


def trade_blocked(a_id, b_id, nation_embargoes, coalition_of, coalition_embargoes) -> bool:
    """Pure function checking if trade between a_id and b_id is blocked.

    Args:
        a_id: Nation/User ID A.
        b_id: Nation/User ID B.
        nation_embargoes: collection of (embargoer_id, target_id) pairs,
            or dict mapping embargoer_id -> iterable of target_ids.
        coalition_of: mapping (dict or callable) from nation_id -> coalition_id.
        coalition_embargoes: collection of (embargoer_col_id, target_col_id) pairs,
            or dict mapping embargoer_col_id -> iterable of target_col_ids.

    Returns:
        True if trade is blocked in either direction, False otherwise.
    """
    if a_id == b_id:
        return False

    # 1. Nation-level embargo check (either direction)
    if nation_embargoes:
        if isinstance(nation_embargoes, dict):
            if b_id in nation_embargoes.get(a_id, ()) or a_id in nation_embargoes.get(b_id, ()):
                return True
        else:
            if (a_id, b_id) in nation_embargoes or (b_id, a_id) in nation_embargoes:
                return True

    # 2. Coalition-level embargo check (either direction)
    if coalition_of and coalition_embargoes:
        col_a = coalition_of(a_id) if callable(coalition_of) else coalition_of.get(a_id)
        col_b = coalition_of(b_id) if callable(coalition_of) else coalition_of.get(b_id)

        if col_a and col_b and col_a != col_b:
            if isinstance(coalition_embargoes, dict):
                if col_b in coalition_embargoes.get(col_a, ()) or col_a in coalition_embargoes.get(col_b, ()):
                    return True
            else:
                if (col_a, col_b) in coalition_embargoes or (col_b, col_a) in coalition_embargoes:
                    return True

    return False


def trade_block_reason(a_id, b_id, nation_embargoes, coalition_of, coalition_embargoes):
    """Pure function returning a human-readable reason string if trade is blocked, else None."""
    if a_id == b_id:
        return None

    if nation_embargoes:
        if isinstance(nation_embargoes, dict):
            if b_id in nation_embargoes.get(a_id, ()):
                return f"Nation-level embargo: nation {a_id} has embargoed nation {b_id}."
            if a_id in nation_embargoes.get(b_id, ()):
                return f"Nation-level embargo: nation {b_id} has embargoed nation {a_id}."
        else:
            if (a_id, b_id) in nation_embargoes:
                return f"Nation-level embargo: nation {a_id} has embargoed nation {b_id}."
            if (b_id, a_id) in nation_embargoes:
                return f"Nation-level embargo: nation {b_id} has embargoed nation {a_id}."

    if coalition_of and coalition_embargoes:
        col_a = coalition_of(a_id) if callable(coalition_of) else coalition_of.get(a_id)
        col_b = coalition_of(b_id) if callable(coalition_of) else coalition_of.get(b_id)

        if col_a and col_b and col_a != col_b:
            if isinstance(coalition_embargoes, dict):
                if col_b in coalition_embargoes.get(col_a, ()):
                    return f"Coalition embargo: coalition {col_a} has embargoed coalition {col_b}."
                if col_a in coalition_embargoes.get(col_b, ()):
                    return f"Coalition embargo: coalition {col_b} has embargoed coalition {col_a}."
            else:
                if (col_a, col_b) in coalition_embargoes:
                    return f"Coalition embargo: coalition {col_a} has embargoed coalition {col_b}."
                if (col_b, col_a) in coalition_embargoes:
                    return f"Coalition embargo: coalition {col_b} has embargoed coalition {col_a}."

    return None

MARKET_PREFERENCE_DEFAULTS = {
    "default_resource": None,
    "hide_unavailable": False,
    "hide_exchange": False,
    "hide_embargoed": True,
    "currency_mode": "all",
    "currency_id": None,
}

def get_market_preferences(db, user_id):
    db.execute(
        "SELECT default_resource, hide_unavailable, hide_exchange, hide_embargoed, "
        "currency_mode, currency_id FROM market_preferences WHERE user_id=%s",
        (user_id,),
    )
    row = db.fetchone()
    if not row:
        return dict(MARKET_PREFERENCE_DEFAULTS)
    return dict(zip(MARKET_PREFERENCE_DEFAULTS.keys(), row))

def upsert_market_preferences(db, user_id, prefs):
    db.execute(
        """
        INSERT INTO market_preferences
            (user_id, default_resource, hide_unavailable, hide_exchange,
             hide_embargoed, currency_mode, currency_id, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (user_id) DO UPDATE SET
            default_resource = EXCLUDED.default_resource,
            hide_unavailable = EXCLUDED.hide_unavailable,
            hide_exchange = EXCLUDED.hide_exchange,
            hide_embargoed = EXCLUDED.hide_embargoed,
            currency_mode = EXCLUDED.currency_mode,
            currency_id = EXCLUDED.currency_id,
            updated_at = NOW()
        """,
        (
            user_id, prefs["default_resource"], prefs["hide_unavailable"],
            prefs["hide_exchange"], prefs["hide_embargoed"],
            prefs["currency_mode"], prefs["currency_id"],
        ),
    )

def record_market_fill(db, offer_id, resource, amount, price, currency_id,
                       gold_price, seller_id, buyer_id):
    """One row per filled market offer, in the trade's own transaction."""
    db.execute(
        """
        INSERT INTO market_fills
            (offer_id, resource, amount, price, currency_id, gold_price,
             seller_id, buyer_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (int(offer_id), resource, int(amount), int(price), currency_id,
         int(gold_price), seller_id, buyer_id),
    )

def get_last_fill_prices(db, resources):
    """{resource: (gold_price, created_at)} of the latest fill per resource."""
    if not resources:
        return {}
    db.execute(
        """
        SELECT DISTINCT ON (resource) resource, gold_price, created_at
        FROM market_fills
        WHERE resource = ANY(%s)
        ORDER BY resource, created_at DESC
        """,
        (list(resources),),
    )
    return {row[0]: (int(row[1]), row[2]) for row in db.fetchall()}
