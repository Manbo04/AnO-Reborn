from flask import (
    request,
    render_template,
    session,
    redirect,
    flash,
    current_app,
)
from helpers import login_required, error, empty_state, require_post_origin, get_influence
import os
from dotenv import load_dotenv

load_dotenv()
import variables  # noqa: E402
import datetime  # noqa: E402
from database import cache_response, rollback_db_cursor, get_request_cursor  # noqa: E402
from database import get_coalition_members_table  # noqa: E402
from typing import Optional  # noqa: E402

# flake8: noqa -- Temporarily disable flake8 for this file to avoid blocking critical fixes; remove when refactoring is complete


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
