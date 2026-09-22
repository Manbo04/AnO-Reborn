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


def can_manage_province_builds(db, actor_id, owner_id) -> bool:
    """Can `actor_id` view/build in a province owned by `owner_id`?

    Always true for the owner acting on their own province. Otherwise only
    true when ALL of the following hold:
      - `owner_id` has explicitly opted in (`users.allow_coalition_builds`)
      - both users are members of the SAME coalition
      - `actor_id`'s role in that coalition is one of the qualifying roles

    Fails closed (returns False) on any lookup error or missing data --
    this gates real account-state access, so an unopted-in member's data
    must never leak because of a schema hiccup or a stale cache.
    """
    try:
        actor_id = int(actor_id)
        owner_id = int(owner_id)
    except (TypeError, ValueError):
        return False

    if actor_id == owner_id:
        return True

    members_tbl = _coalition_members_sql()
    if not members_tbl:
        return False

    try:
        db.execute(
            "SELECT allow_coalition_builds FROM users WHERE id=%s", (owner_id,)
        )
        row = db.fetchone()
        if not row or not row[0]:
            return False

        db.execute(
            f"SELECT colid FROM {members_tbl} WHERE userid=%s", (owner_id,)
        )
        owner_row = db.fetchone()
        if not owner_row or not owner_row[0]:
            return False
        owner_colid = owner_row[0]

        db.execute(
            f"SELECT colid, role FROM {members_tbl} WHERE userid=%s", (actor_id,)
        )
        actor_row = db.fetchone()
        if not actor_row or not actor_row[0]:
            return False
        actor_colid, actor_role = actor_row[0], actor_row[1]

        if actor_colid != owner_colid:
            return False

        return actor_role in BUILD_SHARE_QUALIFYING_ROLES
    except Exception:
        return False
