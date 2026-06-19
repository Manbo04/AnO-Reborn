"""Coalition routes must verify membership in the target coalition (IDOR guard)."""

import os
import uuid

import pytest

from database import get_coalition_members_table, get_db_connection

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_PUBLIC_URL") and not os.getenv("DATABASE_URL"),
    reason="Requires Postgres (DATABASE_PUBLIC_URL or DATABASE_URL)",
)


def _members_table():
    tbl = get_coalition_members_table()
    return tbl or "coalitions_legacy"


def _create_user(db, suffix):
    name = f"guard_{suffix}_{uuid.uuid4().hex[:8]}"
    db.execute(
        "INSERT INTO users (username, email, date, hash, auth_type) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (name, f"{name}@example.test", "2026-05-22", "", "normal"),
    )
    uid = db.fetchone()[0]
    db.execute(
        "INSERT INTO stats (id, location, gold) VALUES (%s, %s, %s) "
        "ON CONFLICT (id) DO UPDATE SET gold = %s",
        (uid, "Grassland", 1_000_000, 1_000_000),
    )
    return uid, name


def _cleanup_coalition(db, col_id, members_tbl):
    db.execute("DELETE FROM colBanksRequests WHERE colId = %s", (col_id,))
    db.execute("DELETE FROM colBanks WHERE colId = %s", (col_id,))
    db.execute(f"DELETE FROM {members_tbl} WHERE colid = %s", (col_id,))
    db.execute("DELETE FROM requests WHERE colId = %s", (col_id,))
    db.execute("DELETE FROM colNames WHERE id = %s", (col_id,))


def _cleanup_user(db, uid, members_tbl):
    db.execute("DELETE FROM colBanksRequests WHERE reqId = %s", (uid,))
    db.execute(f"DELETE FROM {members_tbl} WHERE userid = %s", (uid,))
    db.execute("DELETE FROM requests WHERE reqId = %s", (uid,))
    db.execute("DELETE FROM referral_active_days WHERE referred_user_id = %s", (uid,))
    db.execute("DELETE FROM stats WHERE id = %s", (uid,))
    db.execute("DELETE FROM users WHERE id = %s", (uid,))


def test_leader_cannot_withdraw_from_other_coalition_bank(client):
    """Leader in coalition A must not withdraw from coalition B's bank."""
    members_tbl = _members_table()
    col_a = col_b = leader_id = other_leader_id = None

    with get_db_connection() as conn:
        db = conn.cursor()
        leader_id, _ = _create_user(db, "a")
        other_leader_id, _ = _create_user(db, "b")
        conn.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = leader_id

    r = client.post(
        "/establish_coalition",
        data={
            "type": "Open",
            "name": f"guard_col_a_{uuid.uuid4().hex[:8]}",
            "description": "test coalition A",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303), r.get_data(as_text=True)[:500]

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            f"SELECT colid FROM {members_tbl} WHERE userid = %s",
            (leader_id,),
        )
        col_a = db.fetchone()[0]

    with client.session_transaction() as sess:
        sess["user_id"] = other_leader_id

    r = client.post(
        "/establish_coalition",
        data={
            "type": "Open",
            "name": f"guard_col_b_{uuid.uuid4().hex[:8]}",
            "description": "test coalition B",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303), r.get_data(as_text=True)[:500]

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            f"SELECT colid FROM {members_tbl} WHERE userid = %s",
            (other_leader_id,),
        )
        col_b = db.fetchone()[0]
        db.execute("UPDATE colBanks SET money = %s WHERE colId = %s", (5000, col_b))
        conn.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = leader_id

    r = client.post(
        f"/withdraw_from_bank/{col_b}",
        data={"money": "10"},
        follow_redirects=False,
    )
    assert r.status_code == 400, (
        f"Expected 400 for cross-coalition withdraw, got {r.status_code}"
    )

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT money FROM colBanks WHERE colId = %s", (col_b,))
        row = db.fetchone()
        assert row and int(row[0]) == 5000, "Bank balance must be unchanged after blocked withdraw"

        _cleanup_coalition(db, col_a, members_tbl)
        _cleanup_coalition(db, col_b, members_tbl)
        _cleanup_user(db, leader_id, members_tbl)
        _cleanup_user(db, other_leader_id, members_tbl)
        conn.commit()


def test_leader_cannot_remove_other_coalition_bank_request(client):
    """Leader in coalition A must not delete bank requests for coalition B."""
    members_tbl = _members_table()
    col_a = col_b = leader_id = other_leader_id = member_b_id = None
    bank_request_id = None

    with get_db_connection() as conn:
        db = conn.cursor()
        leader_id, _ = _create_user(db, "ra")
        other_leader_id, _ = _create_user(db, "rb")
        member_b_id, _ = _create_user(db, "mb")
        conn.commit()

    for uid, suffix in (
        (leader_id, f"guard_rm_a_{uuid.uuid4().hex[:8]}"),
        (other_leader_id, f"guard_rm_b_{uuid.uuid4().hex[:8]}"),
    ):
        with client.session_transaction() as sess:
            sess["user_id"] = uid
        r = client.post(
            "/establish_coalition",
            data={"type": "Open", "name": suffix, "description": "test"},
            follow_redirects=False,
        )
        assert r.status_code in (302, 303)

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            f"SELECT colid FROM {members_tbl} WHERE userid = %s",
            (other_leader_id,),
        )
        col_b = db.fetchone()[0]
        db.execute(
            f"INSERT INTO {members_tbl} (colid, userid, role) VALUES (%s, %s, %s) "
            "ON CONFLICT (userid) DO NOTHING",
            (col_b, member_b_id, "member"),
        )
        db.execute(
            "INSERT INTO colBanksRequests (reqId, colId, amount, resource) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (member_b_id, col_b, 5, "money"),
        )
        bank_request_id = db.fetchone()[0]
        db.execute(
            f"SELECT colid FROM {members_tbl} WHERE userid = %s",
            (leader_id,),
        )
        col_a = db.fetchone()[0]
        conn.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = leader_id

    r = client.post(
        f"/remove_bank_request/{bank_request_id}",
        follow_redirects=False,
    )
    assert r.status_code == 400, (
        f"Expected 400 for cross-coalition remove_bank_request, got {r.status_code}"
    )

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            "SELECT id FROM colBanksRequests WHERE id = %s",
            (bank_request_id,),
        )
        assert db.fetchone() is not None, "Request must still exist after blocked delete"

        _cleanup_coalition(db, col_a, members_tbl)
        _cleanup_coalition(db, col_b, members_tbl)
        _cleanup_user(db, leader_id, members_tbl)
        _cleanup_user(db, other_leader_id, members_tbl)
        _cleanup_user(db, member_b_id, members_tbl)
        conn.commit()
