from helpers import error
from database import get_request_cursor, get_coalition_members_table
from typing import Optional


def _coalition_members_sql(table_alias: str = "cm") -> Optional[str]:
    """Validated membership table name for dynamic SQL, or None if absent."""
    tbl = get_coalition_members_table()
    if not tbl or tbl not in ("coalitions_legacy", "coalitions"):
        return None
    return tbl


def _members_tbl() -> str:
    """Resolved membership table name for dynamic SQL."""
    return _coalition_members_sql() or "coalitions_legacy"


def _require_coalition_member(db, user_id, coalition_id, roles=None):
    """Verify user belongs to coalition_id; optionally require role in roles list."""
    members_tbl = _coalition_members_sql()
    if not members_tbl:
        return error(500, "Coalition system unavailable")
    db.execute(
        f"SELECT role FROM {members_tbl} WHERE userid=%s AND colid=%s",
        (user_id, coalition_id),
    )
    row = db.fetchone()
    if not row:
        return error(400, "You are not in this coalition")
    if roles and row[0] not in roles:
        return error(400, "Insufficient permissions")
    return None


def _coalition_id_for_user(db, user_id):
    """Return coalition id if the user is a valid member, else None (cleans orphans)."""
    members_tbl = _coalition_members_sql()
    if not members_tbl:
        return None
    db.execute(f"SELECT colid FROM {members_tbl} WHERE userid=%s", (user_id,))
    row = db.fetchone()
    if not row or not row[0]:
        return None
    coalition_id = row[0]
    db.execute("SELECT id FROM colNames WHERE id=%s", (coalition_id,))
    if not db.fetchone():
        db.execute(f"DELETE FROM {members_tbl} WHERE userid=%s", (user_id,))
        return None
    return coalition_id


# Function for getting the coalition role of a user
def get_user_role(user_id):
    members_tbl = _coalition_members_sql()
    if not members_tbl:
        return None
    with get_request_cursor() as db:
        db.execute(
            f"SELECT role FROM {members_tbl} WHERE userid=%s", (user_id,)
        )
        row = db.fetchone()
        if not row:
            return None
        return row[0]


# Coalition roles allowed to plan/build for a member who has opted in to
# "share-build" access (Kurai's suggestion, seconded by germanicusjuliuscaesar
# for the domestic minister role — suggestions channel, 2026-09-17). Kurai's
# own message named "the banker and leader/second in command" explicitly.
BUILD_SHARE_QUALIFYING_ROLES = (
    "leader",
    "deputy_leader",
    "banker",
    "domestic_minister",
)


# Internal role keys, highest rank first. Permissions always key off these;
# coalitions can only change the DISPLAY name (see get_role_labels).
COALITION_ROLES = (
    "leader",
    "deputy_leader",
    "domestic_minister",
    "banker",
    "tax_collector",
    "foreign_ambassador",
    "general",
    "member",
)

DEFAULT_ROLE_LABELS = {
    "leader": "Leader",
    "deputy_leader": "Deputy Leader",
    "domestic_minister": "Domestic Minister",
    "banker": "Banker",
    "tax_collector": "Tax Collector",
    "foreign_ambassador": "Foreign Ambassador",
    "general": "General",
    "member": "Member",
}

ROLE_LABEL_MAX_LEN = 32

# Coalition information-visibility settings (luciuskonst's Coalition QOL
# wishlist, 2026-09-26). Each key maps to the roles that may see it; the
# defaults reproduce the behaviour from before the setting existed. Leaders
# can always see everything, so a leader can never lock themselves out.
# province_builds / member_revenue additionally require the member to be
# sharing with their coalition (member_shares_with_coalition).
INFO_ACCESS_DEFAULTS = {
    "bank_balances": COALITION_ROLES,
    "bank_logs": ("leader", "deputy_leader", "banker"),
    "tax_logs": ("leader", "deputy_leader", "banker", "tax_collector"),
    "province_builds": BUILD_SHARE_QUALIFYING_ROLES,
    "member_revenue": ("leader", "deputy_leader"),
}

INFO_ACCESS_LABELS = {
    "bank_balances": "Coalition bank balances",
    "bank_logs": "Everyone's bank transactions & contributions",
    "tax_logs": "Coalition tax income log",
    "province_builds": "Plan/build in sharing members' provinces",
    "member_revenue": "Sharing members' Revenue breakdown",
}


def get_role_labels(db, coalition_id) -> dict:
    """{role_key: display name} for a coalition, falling back to defaults."""
    labels = dict(DEFAULT_ROLE_LABELS)
    rows = _optional_fetch(
        db,
        "SELECT role, display_name FROM col_role_names WHERE coalition_id=%s",
        (coalition_id,),
        many=True,
    )
    for role, display_name in rows or []:
        if role in labels and display_name:
            labels[role] = display_name
    return labels


def normalize_info_access(raw) -> dict:
    """Turn the stored JSON (or None) into {key: frozenset(roles)}."""
    access = {}
    raw = raw if isinstance(raw, dict) else {}
    for key, default in INFO_ACCESS_DEFAULTS.items():
        roles = raw.get(key)
        if isinstance(roles, list):
            chosen = {r for r in roles if r in COALITION_ROLES}
        else:
            chosen = set(default)
        chosen.add("leader")
        access[key] = frozenset(chosen)
    return access


def get_coalition_settings(db, coalition_id) -> dict:
    """Leader-configurable coalition settings with safe defaults."""
    settings = {
        "share_builds_default": False,
        "bank_require_requests": False,
        "bank_self_approve": True,
        "info_access": normalize_info_access(None),
    }
    row = _optional_fetch(
        db,
        "SELECT share_builds_default, bank_require_requests, "
        "bank_self_approve, info_access FROM colNames WHERE id=%s",
        (coalition_id,),
    )
    if row:
        settings["share_builds_default"] = bool(row[0])
        settings["bank_require_requests"] = bool(row[1])
        settings["bank_self_approve"] = row[2] is None or bool(row[2])
        settings["info_access"] = normalize_info_access(row[3])
    return settings


def role_can_see(settings, key, role) -> bool:
    return role in settings["info_access"].get(key, ())


def _optional_fetch(db, sql, params, many=False):
    """Run a read inside a SAVEPOINT so a failure (e.g. a column not yet
    migrated) never aborts -- or rolls back -- the caller's transaction.
    Returns None on failure."""
    try:
        db.execute("SAVEPOINT coalition_optional_read")
    except Exception:
        return None
    try:
        db.execute(sql, params)
        result = db.fetchall() if many else db.fetchone()
        db.execute("RELEASE SAVEPOINT coalition_optional_read")
        return result
    except Exception:
        try:
            db.execute("ROLLBACK TO SAVEPOINT coalition_optional_read")
        except Exception:
            pass
        return None


def member_shares_with_coalition(db, owner_id) -> bool:
    """Is `owner_id` sharing builds/revenue with their coalition?

    The member's own explicit toggle always wins. Members who never touched
    it follow their coalition's `share_builds_default`. Fails closed.
    """
    members_tbl = _coalition_members_sql()
    if not members_tbl:
        return False
    row = _optional_fetch(
        db,
        f"""
        SELECT u.allow_coalition_builds, u.coalition_builds_choice_set,
               COALESCE(c.share_builds_default, FALSE)
        FROM users u
        LEFT JOIN {members_tbl} m ON m.userid = u.id
        LEFT JOIN colNames c ON c.id = m.colid
        WHERE u.id = %s
        """,
        (owner_id,),
    )
    if not row:
        return False
    allow, choice_set, coalition_default = row
    if choice_set:
        return bool(allow)
    return bool(allow) or bool(coalition_default)


def _shared_coalition_role(db, actor_id, owner_id):
    """(coalition_id, actor_role) when both are in the same coalition, else None."""
    members_tbl = _coalition_members_sql()
    if not members_tbl:
        return None
    db.execute(f"SELECT colid FROM {members_tbl} WHERE userid=%s", (owner_id,))
    owner_row = db.fetchone()
    if not owner_row or not owner_row[0]:
        return None
    db.execute(f"SELECT colid, role FROM {members_tbl} WHERE userid=%s", (actor_id,))
    actor_row = db.fetchone()
    if not actor_row or not actor_row[0] or actor_row[0] != owner_row[0]:
        return None
    return actor_row[0], actor_row[1]


def _can_access_member_info(db, actor_id, owner_id, key) -> bool:
    try:
        actor_id = int(actor_id)
        owner_id = int(owner_id)
    except (TypeError, ValueError):
        return False
    if actor_id == owner_id:
        return True
    try:
        shared = _shared_coalition_role(db, actor_id, owner_id)
        if not shared:
            return False
        coalition_id, actor_role = shared
        if not member_shares_with_coalition(db, owner_id):
            return False
        return role_can_see(get_coalition_settings(db, coalition_id), key, actor_role)
    except Exception:
        return False


def can_manage_province_builds(db, actor_id, owner_id) -> bool:
    """Can `actor_id` view/build in a province owned by `owner_id`?

    Always true for the owner acting on their own province. Otherwise only
    true when ALL of the following hold:
      - `owner_id` is sharing (explicit opt-in, or never chose and their
        coalition made sharing the default -- member_shares_with_coalition)
      - both users are members of the SAME coalition
      - `actor_id`'s role is allowed `province_builds` by that coalition's
        visibility settings (defaults to BUILD_SHARE_QUALIFYING_ROLES)

    Fails closed (returns False) on any lookup error or missing data --
    this gates real account-state access, so an unshared member's data
    must never leak because of a schema hiccup or a stale cache.
    """
    return _can_access_member_info(db, actor_id, owner_id, "province_builds")


def can_view_member_revenue(db, actor_id, owner_id) -> bool:
    """Same gate as can_manage_province_builds, for the `member_revenue` key."""
    return _can_access_member_info(db, actor_id, owner_id, "member_revenue")


def coalition_embargoes_table_exists(db) -> bool:
    """Graceful degradation: check if coalition_embargoes exists."""
    try:
        db.execute("SELECT to_regclass('coalition_embargoes') IS NOT NULL")
        row = db.fetchone()
        return bool(row[0] if not isinstance(row, dict) else list(row.values())[0])
    except Exception:
        return False


def is_coalition_embargoed(db, embargoer_col_id, target_col_id) -> bool:
    """Check if embargoer_col_id has an active embargo on target_col_id."""
    if not embargoer_col_id or not target_col_id or embargoer_col_id == target_col_id:
        return False
    if not coalition_embargoes_table_exists(db):
        return False
    db.execute(
        "SELECT 1 FROM coalition_embargoes WHERE embargoer_coalition_id=%s AND target_coalition_id=%s",
        (embargoer_col_id, target_col_id),
    )
    return db.fetchone() is not None


def are_coalitions_embargoed(db, col_a_id, col_b_id) -> bool:
    """Check if either coalition has an active embargo on the other."""
    if not col_a_id or not col_b_id or col_a_id == col_b_id:
        return False
    if not coalition_embargoes_table_exists(db):
        return False
    db.execute(
        "SELECT 1 FROM coalition_embargoes WHERE "
        "(embargoer_coalition_id=%s AND target_coalition_id=%s) OR "
        "(embargoer_coalition_id=%s AND target_coalition_id=%s)",
        (col_a_id, col_b_id, col_b_id, col_a_id),
    )
    return db.fetchone() is not None


def add_coalition_embargo(db, embargoer_col_id, target_col_id, created_by_user_id) -> bool:
    """Add a coalition-level embargo."""
    if not coalition_embargoes_table_exists(db):
        return False
    db.execute(
        "INSERT INTO coalition_embargoes (embargoer_coalition_id, target_coalition_id, created_by) "
        "VALUES (%s, %s, %s) "
        "ON CONFLICT (embargoer_coalition_id, target_coalition_id) DO NOTHING",
        (embargoer_col_id, target_col_id, created_by_user_id),
    )
    return True


def remove_coalition_embargo(db, embargoer_col_id, target_col_id) -> bool:
    """Lift a coalition-level embargo."""
    if not coalition_embargoes_table_exists(db):
        return False
    db.execute(
        "DELETE FROM coalition_embargoes WHERE embargoer_coalition_id=%s AND target_coalition_id=%s",
        (embargoer_col_id, target_col_id),
    )
    return True


def list_coalition_embargoes(db, coalition_id) -> list:
    """List of (target_coalition_id, target_coalition_name, created_at) embargoed by coalition_id."""
    if not coalition_id or not coalition_embargoes_table_exists(db):
        return []
    db.execute(
        "SELECT ce.target_coalition_id, c.name, ce.created_at "
        "FROM coalition_embargoes ce "
        "JOIN colNames c ON c.id = ce.target_coalition_id "
        "WHERE ce.embargoer_coalition_id=%s ORDER BY c.name ASC",
        (coalition_id,),
    )
    return db.fetchall()


def list_coalitions_embargoing(db, coalition_id) -> list:
    """List of (embargoer_coalition_id, embargoer_coalition_name, created_at) embargoing coalition_id."""
    if not coalition_id or not coalition_embargoes_table_exists(db):
        return []
    db.execute(
        "SELECT ce.embargoer_coalition_id, c.name, ce.created_at "
        "FROM coalition_embargoes ce "
        "JOIN colNames c ON c.id = ce.embargoer_coalition_id "
        "WHERE ce.target_coalition_id=%s ORDER BY c.name ASC",
        (coalition_id,),
    )
    return db.fetchall()


def post_coalition_members_news(db, coalition_id, message: str) -> None:
    """Post news item to every member of coalition_id."""
    members_tbl = _coalition_members_sql()
    if not members_tbl or not coalition_id:
        return
    db.execute(f"SELECT userid FROM {members_tbl} WHERE colid = %s", (coalition_id,))
    rows = db.fetchall()
    if not rows:
        return
    uids = [r[0] for r in rows]
    db.executemany(
        "INSERT INTO news (destination_id, message) VALUES (%s, %s)",
        [(uid, message) for uid in uids],
    )

