"""The one write path for gold and stockpiled resources.

Every change to stats.gold or user_economy should go through here, so
that "can this player afford it?" and "take the money" are one atomic
statement instead of a read followed by a separate write (the shape of
most double-spend bugs found since 2026-09). scripts/check_economy_writes.py
blocks new raw writes elsewhere.

Three kinds of change:
  spend_*   all-or-nothing; raises InsufficientFunds and changes nothing
            visible once the caller rolls back.
  take_*    clamped at zero (upkeep, penalties, theft); returns what was taken.
  credit_*  add.
"""

from psycopg2.extras import execute_batch


class InsufficientFunds(Exception):
    def __init__(self, resource, needed):
        super().__init__(f"not enough {resource} (need {needed:,})")
        self.resource = resource
        self.needed = needed


def _amount(value):
    value = int(round(value))
    if value < 0:
        raise ValueError("ledger amounts must be non-negative")
    return value


# --- gold -------------------------------------------------------------

def credit_gold(db, user_id, amount):
    amount = _amount(amount)
    if amount:
        db.execute("UPDATE stats SET gold=gold+%s WHERE id=%s", (amount, user_id))


def spend_gold(db, user_id, amount):
    """Take exactly amount or raise InsufficientFunds. Returns the new balance."""
    amount = _amount(amount)
    db.execute(
        "UPDATE stats SET gold=gold-%s WHERE id=%s AND gold>=%s RETURNING gold",
        (amount, user_id, amount),
    )
    row = db.fetchone()
    if row is None:
        raise InsufficientFunds("money", amount)
    return row[0] if not isinstance(row, dict) else row["gold"]


def take_gold(db, user_id, amount):
    """Take up to amount, never below zero. Returns how much was taken."""
    amount = _amount(amount)
    db.execute(
        """
        UPDATE stats s SET gold = GREATEST(0, s.gold - %s)
        FROM (SELECT gold FROM stats WHERE id = %s FOR UPDATE) old
        WHERE s.id = %s
        RETURNING old.gold - s.gold
        """,
        (amount, user_id, user_id),
    )
    row = db.fetchone()
    if row is None:
        return 0
    return int(row[0] if not isinstance(row, dict) else list(row.values())[0])


# --- resources ----------------------------------------------------------

_ENSURE_ROW = """
    INSERT INTO user_economy (user_id, resource_id, quantity)
    SELECT %s, rd.resource_id, 0
    FROM resource_dictionary rd
    WHERE rd.name=%s
    ON CONFLICT (user_id, resource_id) DO NOTHING
"""


def credit_resources(db, user_id, amounts):
    """amounts: {resource_name: quantity}."""
    for name, q in amounts.items():
        q = _amount(q)
        if not q:
            continue
        db.execute(_ENSURE_ROW, (user_id, name))
        db.execute(
            """
            WITH rid AS (SELECT resource_id FROM resource_dictionary WHERE name=%s)
            UPDATE user_economy ue SET quantity = ue.quantity + %s
            FROM rid
            WHERE ue.user_id=%s AND ue.resource_id = rid.resource_id
            RETURNING ue.quantity
            """,
            (name, q, user_id),
        )
        db.fetchone()


def spend_resources(db, user_id, amounts):
    """Take exactly these amounts or raise InsufficientFunds (caller rolls back)."""
    for name, q in amounts.items():
        q = _amount(q)
        if not q:
            continue
        db.execute(
            """
            WITH rid AS (SELECT resource_id FROM resource_dictionary WHERE name=%s)
            UPDATE user_economy ue SET quantity = ue.quantity - %s
            FROM rid
            WHERE ue.user_id=%s AND ue.resource_id = rid.resource_id
              AND ue.quantity >= %s
            RETURNING ue.quantity
            """,
            (name, q, user_id, q),
        )
        if db.fetchone() is None:
            raise InsufficientFunds(name, q)


def take_resources(db, user_id, amounts):
    """Take up to these amounts, never below zero."""
    items = [(name, _amount(q)) for name, q in amounts.items() if int(q)]
    if not items:
        return
    execute_batch(
        db,
        """
        UPDATE user_economy ue SET quantity = GREATEST(0, ue.quantity - %s)
        FROM resource_dictionary rd
        WHERE ue.user_id = %s AND ue.resource_id = rd.resource_id AND rd.name = %s
        """,
        [(q, user_id, name) for name, q in items],
    )


def adjust_resources(db, user_id, deltas):
    """Signed deltas: positives are credited, negatives taken (clamped at zero)."""
    credit_resources(db, user_id, {n: d for n, d in deltas.items() if d > 0})
    take_resources(db, user_id, {n: -d for n, d in deltas.items() if d < 0})
