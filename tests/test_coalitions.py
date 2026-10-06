"""Founding a coalition: the colNames row exists and the founder is its leader.

Replaces a legacy HTTP test that depended on a login made by test_auth.py's
module-level session (order-dependent)."""
import uuid

import pytest

from database import get_coalition_members_table, get_db_connection
from tests._db_cleanup import purge_users

pytestmark = pytest.mark.no_server


def test_establish_coalition():
    from app import app
    from tests._session import mark_validated

    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    name = f"col_{uuid.uuid4().hex[:8]}"
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            "INSERT INTO users (username, email, date, hash, auth_type) "
            "VALUES (%s, %s, '2026-10-06', 'x', 'normal') RETURNING id",
            (name, f"{name}@example.invalid"),
        )
        uid = db.fetchone()[0]
        db.execute("INSERT INTO stats (id, location) VALUES (%s, 'Grassland')", (uid,))
        conn.commit()
    col_name = f"Test Coalition {uuid.uuid4().hex[:6]}"
    members_tbl = get_coalition_members_table()
    try:
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess["user_id"] = uid
                mark_validated(sess)
            resp = client.post(
                "/establish_coalition",
                data={"type": "Open", "name": col_name, "description": "for testing"},
            )
            assert resp.status_code in (302, 303), resp.status_code
        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute("SELECT id FROM colNames WHERE name = %s", (col_name,))
            row = db.fetchone()
            assert row, "coalition row not created"
            db.execute(f"SELECT role FROM {members_tbl} WHERE colid = %s AND userid = %s", (row[0], uid))
            assert db.fetchone()[0] == "leader"
    finally:
        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute(f"DELETE FROM {members_tbl} WHERE userid = %s", (uid,))
            db.execute("DELETE FROM colNames WHERE name = %s", (col_name,))
            purge_users(db, [uid])
            conn.commit()
