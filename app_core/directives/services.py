"""Directives: 7-day national boosts bought with gold.

Single source of truth for what each directive does and costs. Consumers:
  * tax_formula.compute_tax_income(tax_multiplier=...) via tax_multiplier_for()
  * province buy routes via land_price_multiplier_for()
"""
from app_core.economy import ledger

DURATION_DAYS = 7

DIRECTIVES = {
    "tax_drive": {
        "name": "Tax Drive",
        "summary": "+5% tax income for 7 days.",
        "tax_multiplier": 1.05,
    },
    "land_drive": {
        "name": "Land Drive",
        "summary": "-10% price of land and cities for 7 days.",
        "land_multiplier": 0.90,
    },
}

# Fee, in hours of the nation s own gross tax income. The Tax Drive pays back
# about 8.4 hours of income over its week, so the fee is below break-even but
# never free; it scales with the size of the nation.
COST_HOURS = 4
MIN_COST = 50_000


def tax_multiplier_for(active_keys):
    mult = 1.0
    for key in active_keys or ():
        mult *= DIRECTIVES.get(key, {}).get("tax_multiplier", 1.0)
    return mult


def land_price_multiplier_for(active_keys):
    mult = 1.0
    for key in active_keys or ():
        mult *= DIRECTIVES.get(key, {}).get("land_multiplier", 1.0)
    return mult


def _col(row, index, name):
    return row[name] if isinstance(row, dict) else row[index]


def active_keys_batch(db, user_ids):
    """{user_id: set(keys)} for directives that have not expired."""
    out = {}
    ids = list(user_ids or [])
    if not ids:
        return out
    db.execute(
        "SELECT user_id, directive_key FROM directives "
        "WHERE user_id = ANY(%s) AND expires_at > now()",
        (ids,),
    )
    for row in db.fetchall():
        out.setdefault(_col(row, 0, "user_id"), set()).add(_col(row, 1, "directive_key"))
    return out


def active_keys(db, user_id):
    return active_keys_batch(db, [user_id]).get(user_id, set())


def activation_cost(hourly_income):
    return max(MIN_COST, int(hourly_income or 0) * COST_HOURS)


def list_for_user(db, user_id, hourly_income):
    """Rows for the page: each directive with state and current fee."""
    db.execute(
        "SELECT directive_key, expires_at FROM directives "
        "WHERE user_id = %s AND expires_at > now()",
        (user_id,),
    )
    expiry = {_col(r, 0, "directive_key"): _col(r, 1, "expires_at") for r in db.fetchall()}
    cost = activation_cost(hourly_income)
    return [
        {"key": key, "name": d["name"], "summary": d["summary"], "cost": cost,
         "expires_at": expiry.get(key)}
        for key, d in DIRECTIVES.items()
    ]


def activate(db, user_id, key, hourly_income):
    """Returns (ok, message). Charges the fee and starts the 7-day window."""
    if key not in DIRECTIVES:
        return False, "Unknown directive."
    db.execute("SELECT pg_advisory_xact_lock(%s)", (user_id,))
    if key in active_keys(db, user_id):
        return False, "That directive is already active."
    cost = activation_cost(hourly_income)
    try:
        ledger.spend_gold(db, user_id, cost)
    except ledger.InsufficientFunds:
        return False, "Not enough gold for that directive."
    db.execute(
        "INSERT INTO directives (user_id, directive_key, activated_at, expires_at) "
        "VALUES (%s, %s, now(), now() + make_interval(days => %s)) "
        "ON CONFLICT (user_id, directive_key) DO UPDATE "
        "SET activated_at = now(), expires_at = EXCLUDED.expires_at",
        (user_id, key, DURATION_DAYS),
    )
    return True, f"{DIRECTIVES[key]['name']} is active for {DURATION_DAYS} days."
