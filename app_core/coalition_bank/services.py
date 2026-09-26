"""Coalition bank trade requests + coalition bond insurance (Kurai,
#suggestions, 2026-09-24/26; schema in migration 0082).

Bank trades: a member proposes "I give X of A, the bank gives me Y of B".
Their side is taken into escrow on submit, so an accepted trade can never
come up short; a leader/deputy/banker accepts (both sides move in the same
transaction) or declines (escrow refunded). Kept separate from the
withdraw-request flow in app_core/coalitions/routes.py on purpose -- that
one is a one-way payout, this is a two-sided swap.

Bond insurance: leadership picks which members are insured. The payout
and recovery themselves happen in app_core/game_ticks/bond_tick.py; this
module only manages the roster and what the page shows.
"""
import variables

from app_core.coalitions.repositories import _coalition_members_sql

OFFICER_ROLES = ("leader", "deputy_leader", "banker")
BANK_RESOURCES = ["money"] + list(variables.RESOURCES)
MAX_PENDING_TRADES_PER_MEMBER = 5


def resource_label(resource):
    return "Money" if resource == "money" else resource.replace("_", " ").capitalize()


def get_role(db, user_id, coalition_id):
    tbl = _coalition_members_sql()
    if not tbl:
        return None
    db.execute(f"SELECT role FROM {tbl} WHERE userid=%s AND colid=%s", (user_id, coalition_id))
    row = db.fetchone()
    return row[0] if row else None


def get_officer_ids(db, coalition_id, exclude=None):
    tbl = _coalition_members_sql()
    if not tbl:
        return []
    db.execute(
        f"SELECT userid FROM {tbl} WHERE colid=%s AND role IN ('leader', 'deputy_leader', 'banker')",
        (coalition_id,),
    )
    return [r[0] for r in db.fetchall() if r[0] != exclude]


def get_coalition_name(db, coalition_id):
    db.execute("SELECT name FROM colNames WHERE id=%s", (coalition_id,))
    row = db.fetchone()
    return row[0] if row else None


def _username(db, user_id):
    db.execute("SELECT username FROM users WHERE id=%s", (user_id,))
    row = db.fetchone()
    return row[0] if row else f"Nation #{user_id}"


def _news(db, user_ids, message):
    for uid in set(u for u in user_ids if u):
        db.execute("INSERT INTO news (destination_id, message) VALUES (%s, %s)", (uid, message))


def _resource_id(db, resource):
    db.execute("SELECT resource_id FROM resource_dictionary WHERE name = %s", (resource,))
    row = db.fetchone()
    return row[0] if row else None


def _take_from_player(db, user_id, resource, amount):
    """Atomically deduct; False if the player doesn't have enough."""
    if resource == "money":
        db.execute(
            "UPDATE stats SET gold = gold - %s WHERE id = %s AND gold >= %s RETURNING gold",
            (amount, user_id, amount),
        )
        return db.fetchone() is not None
    resource_id = _resource_id(db, resource)
    if resource_id is None:
        return False
    db.execute(
        """
        UPDATE user_economy SET quantity = quantity - %s
        WHERE user_id = %s AND resource_id = %s AND quantity >= %s
        RETURNING quantity
        """,
        (amount, user_id, resource_id, amount),
    )
    return db.fetchone() is not None


def _give_to_player(db, user_id, resource, amount):
    if resource == "money":
        db.execute("UPDATE stats SET gold = gold + %s WHERE id = %s", (amount, user_id))
        return
    resource_id = _resource_id(db, resource)
    db.execute(
        """
        INSERT INTO user_economy (user_id, resource_id, quantity)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id, resource_id)
        DO UPDATE SET quantity = user_economy.quantity + EXCLUDED.quantity
        """,
        (user_id, resource_id, amount),
    )


def _log_bank_txn(db, coalition_id, user_id, actor_id, resource, amount, direction):
    try:
        db.execute("SAVEPOINT bank_trade_log")
        db.execute(
            """
            INSERT INTO col_bank_transactions
                (coalition_id, user_id, actor_id, resource, amount, direction)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (coalition_id, user_id, actor_id, resource, amount, direction),
        )
        db.execute("RELEASE SAVEPOINT bank_trade_log")
    except Exception:
        db.execute("ROLLBACK TO SAVEPOINT bank_trade_log")


def _parse_amount(raw):
    try:
        value = int(str(raw).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


# ---------------------------------------------------------------- trades

def propose_trade(db, user_id, coalition_id, give_resource, give_amount, want_resource, want_amount, note):
    """Returns (ok, message)."""
    if not get_role(db, user_id, coalition_id):
        return False, "You're not in this coalition."
    if give_resource not in BANK_RESOURCES or want_resource not in BANK_RESOURCES:
        return False, "Pick valid resources."
    if give_resource == want_resource:
        return False, "You can't trade a resource for itself."
    give_amount = _parse_amount(give_amount)
    want_amount = _parse_amount(want_amount)
    if not give_amount or not want_amount:
        return False, "Enter whole amounts greater than 0."
    note = (note or "").strip()[:200] or None

    db.execute("SELECT pg_advisory_xact_lock(%s)", (user_id,))
    db.execute(
        "SELECT COUNT(*) FROM col_bank_trades WHERE user_id=%s AND status='pending'",
        (user_id,),
    )
    if db.fetchone()[0] >= MAX_PENDING_TRADES_PER_MEMBER:
        return False, f"You already have {MAX_PENDING_TRADES_PER_MEMBER} trades waiting. Cancel one first."

    if not _take_from_player(db, user_id, give_resource, give_amount):
        return False, f"You don't have {give_amount:,} {resource_label(give_resource).lower()}."

    db.execute(
        """
        INSERT INTO col_bank_trades
            (coalition_id, user_id, give_resource, give_amount, want_resource, want_amount, note)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (coalition_id, user_id, give_resource, give_amount, want_resource, want_amount, note),
    )
    trade_id = db.fetchone()[0]
    name = _username(db, user_id)
    _news(
        db,
        get_officer_ids(db, coalition_id, exclude=user_id),
        f"{name} sent a bank trade: {give_amount:,} {resource_label(give_resource).lower()} for "
        f"{want_amount:,} {resource_label(want_resource).lower()} from the coalition bank. "
        f"Review it under Bank trades on your coalition page.",
    )
    return True, (
        f"Trade #{trade_id} sent to your bankers. Your {give_amount:,} "
        f"{resource_label(give_resource).lower()} is held until they accept or decline."
    )


def _lock_pending_trade(db, trade_id):
    db.execute(
        """
        SELECT id, coalition_id, user_id, give_resource, give_amount, want_resource, want_amount, status
        FROM col_bank_trades WHERE id=%s FOR UPDATE
        """,
        (trade_id,),
    )
    return db.fetchone()


def _close_trade(db, trade_id, status, actor_id):
    db.execute(
        "UPDATE col_bank_trades SET status=%s, resolved_at=NOW(), resolved_by=%s WHERE id=%s",
        (status, actor_id, trade_id),
    )


def accept_trade(db, actor_id, trade_id):
    """Returns (ok, message, coalition_id)."""
    row = _lock_pending_trade(db, trade_id)
    if not row:
        return False, "Trade not found.", None
    _, coalition_id, user_id, give_res, give_amt, want_res, want_amt, status = row
    if get_role(db, actor_id, coalition_id) not in OFFICER_ROLES:
        return False, "Only the leader, deputies or bankers can accept bank trades.", coalition_id
    if status != "pending":
        return False, "That trade was already handled.", coalition_id
    if give_res not in BANK_RESOURCES or want_res not in BANK_RESOURCES:
        return False, "Invalid trade.", coalition_id

    if not get_role(db, user_id, coalition_id):
        _give_to_player(db, user_id, give_res, give_amt)
        _close_trade(db, trade_id, "declined", actor_id)
        _news(db, [user_id], f"Your bank trade #{trade_id} was cancelled because you left the coalition. "
                             f"Your {give_amt:,} {resource_label(give_res).lower()} was returned.")
        return False, "That member left the coalition; their escrow was refunded.", coalition_id

    db.execute(
        f"UPDATE colBanks SET {want_res} = {want_res} - %s WHERE colId=%s AND {want_res} >= %s RETURNING colId",
        (want_amt, coalition_id, want_amt),
    )
    if not db.fetchone():
        return False, (
            f"The bank doesn't have {want_amt:,} {resource_label(want_res).lower()}. "
            f"Deposit more or decline the trade."
        ), coalition_id
    db.execute(
        f"UPDATE colBanks SET {give_res} = {give_res} + %s WHERE colId=%s",
        (give_amt, coalition_id),
    )
    _give_to_player(db, user_id, want_res, want_amt)
    _close_trade(db, trade_id, "accepted", actor_id)
    _log_bank_txn(db, coalition_id, user_id, actor_id, give_res, give_amt, "deposit")
    _log_bank_txn(db, coalition_id, user_id, actor_id, want_res, want_amt, "withdraw")
    _news(
        db,
        [user_id],
        f"{_username(db, actor_id)} accepted your bank trade #{trade_id}: you received {want_amt:,} "
        f"{resource_label(want_res).lower()} for {give_amt:,} {resource_label(give_res).lower()}.",
    )
    return True, f"Trade #{trade_id} accepted.", coalition_id


def decline_trade(db, actor_id, trade_id, cancel=False):
    """Officer decline, or the proposer cancelling their own (cancel=True).
    Either way the escrowed side goes back. Returns (ok, message, coalition_id)."""
    row = _lock_pending_trade(db, trade_id)
    if not row:
        return False, "Trade not found.", None
    _, coalition_id, user_id, give_res, give_amt, _, _, status = row
    if cancel:
        if actor_id != user_id:
            return False, "That isn't your trade.", coalition_id
    elif get_role(db, actor_id, coalition_id) not in OFFICER_ROLES:
        return False, "Only the leader, deputies or bankers can decline bank trades.", coalition_id
    if status != "pending":
        return False, "That trade was already handled.", coalition_id

    _give_to_player(db, user_id, give_res, give_amt)
    _close_trade(db, trade_id, "cancelled" if cancel else "declined", actor_id)
    if not cancel:
        _news(
            db,
            [user_id],
            f"{_username(db, actor_id)} declined your bank trade #{trade_id}. Your {give_amt:,} "
            f"{resource_label(give_res).lower()} was returned.",
        )
    return True, f"Trade #{trade_id} {'cancelled' if cancel else 'declined'}; escrow returned.", coalition_id


def get_trades_page(db, user_id, coalition_id):
    role = get_role(db, user_id, coalition_id)
    is_officer = role in OFFICER_ROLES
    db.execute(
        f"""
        SELECT t.id, t.user_id, u.username, t.give_resource, t.give_amount,
               t.want_resource, t.want_amount, t.note, t.status, t.created_at,
               t.resolved_at, r.username
        FROM col_bank_trades t
        JOIN users u ON u.id = t.user_id
        LEFT JOIN users r ON r.id = t.resolved_by
        WHERE t.coalition_id = %s {'' if is_officer else 'AND t.user_id = %s'}
        ORDER BY (t.status = 'pending') DESC, t.id DESC
        LIMIT 60
        """,
        (coalition_id,) if is_officer else (coalition_id, user_id),
    )
    trades = [
        {
            "id": r[0], "user_id": r[1], "username": r[2],
            "give_resource": r[3], "give_label": resource_label(r[3]), "give_amount": r[4],
            "want_resource": r[5], "want_label": resource_label(r[5]), "want_amount": r[6],
            "note": r[7], "status": r[8], "created_at": r[9], "resolved_at": r[10], "resolved_by": r[11],
        }
        for r in db.fetchall()
    ]
    bank = {}
    cols = ", ".join(BANK_RESOURCES)
    db.execute(f"SELECT {cols} FROM colBanks WHERE colId=%s", (coalition_id,))
    row = db.fetchone()
    if row:
        bank = {res: int(val or 0) for res, val in zip(BANK_RESOURCES, row)}
    return {
        "role": role,
        "is_officer": is_officer,
        "trades": trades,
        "bank": bank,
        "resources": [(r, resource_label(r)) for r in BANK_RESOURCES],
        "max_pending": MAX_PENDING_TRADES_PER_MEMBER,
    }


# ------------------------------------------------------------- insurance

def set_insured(db, actor_id, coalition_id, member_id, insured):
    """Returns (ok, message)."""
    if get_role(db, actor_id, coalition_id) not in OFFICER_ROLES:
        return False, "Only the leader, deputies or bankers can change bond insurance."
    if insured:
        if not get_role(db, member_id, coalition_id):
            return False, "That nation isn't in your coalition."
        db.execute(
            """
            INSERT INTO coalition_bond_insurance (coalition_id, user_id, added_by)
            VALUES (%s, %s, %s) ON CONFLICT DO NOTHING
            """,
            (coalition_id, member_id, actor_id),
        )
        _news(db, [member_id], "Your coalition now insures your bonds: if you default, the coalition bank "
                               "pays your lender and you repay the bank instead.")
        return True, f"{_username(db, member_id)} is now insured."
    db.execute(
        "DELETE FROM coalition_bond_insurance WHERE coalition_id=%s AND user_id=%s",
        (coalition_id, member_id),
    )
    return True, f"{_username(db, member_id)} is no longer insured."


def get_insurance_page(db, user_id, coalition_id):
    role = get_role(db, user_id, coalition_id)
    tbl = _coalition_members_sql()
    db.execute(
        f"""
        SELECT m.userid, u.username, m.role, (i.user_id IS NOT NULL) AS insured,
               COALESCE((SELECT SUM(b.principal) FROM bonds b
                         WHERE b.issuer_id = m.userid AND b.status = 'active'), 0) AS active_debt
        FROM {tbl} m
        JOIN users u ON u.id = m.userid
        LEFT JOIN coalition_bond_insurance i ON i.coalition_id = m.colid AND i.user_id = m.userid
        WHERE m.colid = %s
        ORDER BY insured DESC, u.username
        """,
        (coalition_id,),
    )
    members = [
        {"id": r[0], "username": r[1], "role": r[2], "insured": r[3], "active_debt": float(r[4] or 0)}
        for r in db.fetchall()
    ]
    db.execute(
        """
        SELECT b.id, b.issuer_id, iu.username, lu.username, b.insurance_paid, b.insurer_owed, b.resolved_at
        FROM bonds b
        JOIN users iu ON iu.id = b.issuer_id
        LEFT JOIN users lu ON lu.id = b.lender_id
        WHERE b.insurer_coalition_id = %s
        ORDER BY b.resolved_at DESC NULLS LAST
        LIMIT 30
        """,
        (coalition_id,),
    )
    claims = [
        {"bond_id": r[0], "issuer_id": r[1], "issuer": r[2], "lender": r[3] or "—",
         "paid": float(r[4] or 0), "owed": float(r[5] or 0), "when": r[6]}
        for r in db.fetchall()
    ]
    db.execute("SELECT money FROM colBanks WHERE colId=%s", (coalition_id,))
    row = db.fetchone()
    return {
        "role": role,
        "is_officer": role in OFFICER_ROLES,
        "members": members,
        "claims": claims,
        "bank_money": int(row[0] or 0) if row else 0,
        "me_insured": any(m["insured"] and m["id"] == user_id for m in members),
    }
