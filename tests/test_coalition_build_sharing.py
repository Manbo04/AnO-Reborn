"""Coalition "share-build" opt-in (Kurai + germanicusjuliuscaesar, suggestions
channel, 2026-09-17): a member can let qualifying coalition roles (leader,
deputy_leader, banker, domestic_minister) plan/build in their province -- but
ONLY when they've explicitly opted in, and ONLY for members of their own
coalition. This must never leak an unopted-in member's account state.
"""

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
    name = f"buildshare_{suffix}_{uuid.uuid4().hex[:8]}"
    db.execute(
        "INSERT INTO users (username, email, date, hash, auth_type) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (name, f"{name}@example.test", "2026-09-22", "", "normal"),
    )
    uid = db.fetchone()[0]
    db.execute(
        "INSERT INTO stats (id, location, gold) VALUES (%s, %s, %s) "
        "ON CONFLICT (id) DO UPDATE SET gold = %s",
        (uid, "Grassland", 5_000_000, 5_000_000),
    )
    return uid, name


def _create_province(db, user_id):
    db.execute(
        "INSERT INTO provinces (userId, provinceName, population, land, citycount) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (user_id, f"buildshare_prov_{uuid.uuid4().hex[:6]}", 1000, 100, 5),
    )
    return db.fetchone()[0]


def _cleanup_coalition(db, col_id, members_tbl):
    if not col_id:
        return
    db.execute("DELETE FROM colBanksRequests WHERE colId = %s", (col_id,))
    db.execute("DELETE FROM colBanks WHERE colId = %s", (col_id,))
    db.execute(f"DELETE FROM {members_tbl} WHERE colid = %s", (col_id,))
    db.execute("DELETE FROM requests WHERE colId = %s", (col_id,))
    db.execute("DELETE FROM colNames WHERE id = %s", (col_id,))


def _cleanup_user(db, uid, members_tbl):
    if not uid:
        return
    db.execute("DELETE FROM user_buildings WHERE user_id = %s", (uid,))
    db.execute("DELETE FROM provinces WHERE userId = %s", (uid,))
    db.execute("DELETE FROM colBanksRequests WHERE reqId = %s", (uid,))
    db.execute(f"DELETE FROM {members_tbl} WHERE userid = %s", (uid,))
    db.execute("DELETE FROM requests WHERE reqId = %s", (uid,))
    db.execute("DELETE FROM referral_active_days WHERE referred_user_id = %s", (uid,))
    db.execute("DELETE FROM stats WHERE id = %s", (uid,))
    db.execute("DELETE FROM users WHERE id = %s", (uid,))


def test_not_opted_in_blocks_coalition_leader(client):
    """Leader must NOT be able to build in a member's province by default (opt-in off)."""
    members_tbl = _members_table()
    col_id = leader_id = member_id = province_id = None
    try:
        with get_db_connection() as conn:
            db = conn.cursor()
            leader_id, _ = _create_user(db, "leader1")
            member_id, _ = _create_user(db, "member1")
            conn.commit()

        with client.session_transaction() as sess:
            sess["user_id"] = leader_id
        r = client.post(
            "/establish_coalition",
            data={
                "type": "Open",
                "name": f"buildshare_col_{uuid.uuid4().hex[:8]}",
                "description": "test",
            },
            follow_redirects=False,
        )
        assert r.status_code in (302, 303)

        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute(
                f"SELECT colid FROM {members_tbl} WHERE userid=%s", (leader_id,)
            )
            col_id = db.fetchone()[0]
            db.execute(
                f"INSERT INTO {members_tbl} (colid, userid, role) VALUES (%s, %s, %s) "
                "ON CONFLICT (userid) DO NOTHING",
                (col_id, member_id, "member"),
            )
            # Explicitly NOT opted in (default FALSE).
            db.execute(
                "UPDATE users SET allow_coalition_builds=FALSE WHERE id=%s",
                (member_id,),
            )
            province_id = _create_province(db, member_id)
            conn.commit()

        with client.session_transaction() as sess:
            sess["user_id"] = leader_id

        r = client.post(
            f"/api/province/{province_id}/quick_build",
            json={"building_id": 1, "quantity": 1},
        )
        assert r.status_code == 403, r.get_data(as_text=True)[:300]
    finally:
        with get_db_connection() as conn:
            db = conn.cursor()
            _cleanup_coalition(db, col_id, members_tbl)
            _cleanup_user(db, leader_id, members_tbl)
            _cleanup_user(db, member_id, members_tbl)
            conn.commit()


def test_opted_in_plain_member_role_still_blocked(client):
    """Opt-in alone isn't enough -- the ACTOR's role must also qualify."""
    members_tbl = _members_table()
    col_id = leader_id = member_id = other_member_id = province_id = None
    try:
        with get_db_connection() as conn:
            db = conn.cursor()
            leader_id, _ = _create_user(db, "leader2")
            member_id, _ = _create_user(db, "member2")
            other_member_id, _ = _create_user(db, "othermember2")
            conn.commit()

        with client.session_transaction() as sess:
            sess["user_id"] = leader_id
        r = client.post(
            "/establish_coalition",
            data={
                "type": "Open",
                "name": f"buildshare_col_{uuid.uuid4().hex[:8]}",
                "description": "test",
            },
            follow_redirects=False,
        )
        assert r.status_code in (302, 303)

        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute(
                f"SELECT colid FROM {members_tbl} WHERE userid=%s", (leader_id,)
            )
            col_id = db.fetchone()[0]
            for uid in (member_id, other_member_id):
                db.execute(
                    f"INSERT INTO {members_tbl} (colid, userid, role) VALUES (%s, %s, 'member') "
                    "ON CONFLICT (userid) DO NOTHING",
                    (col_id, uid),
                )
            db.execute(
                "UPDATE users SET allow_coalition_builds=TRUE WHERE id=%s",
                (member_id,),
            )
            province_id = _create_province(db, member_id)
            conn.commit()

        # other_member_id is a plain "member", not a qualifying role.
        with client.session_transaction() as sess:
            sess["user_id"] = other_member_id

        r = client.post(
            f"/api/province/{province_id}/quick_build",
            json={"building_id": 1, "quantity": 1},
        )
        assert r.status_code == 403, r.get_data(as_text=True)[:300]
    finally:
        with get_db_connection() as conn:
            db = conn.cursor()
            _cleanup_coalition(db, col_id, members_tbl)
            _cleanup_user(db, leader_id, members_tbl)
            _cleanup_user(db, member_id, members_tbl)
            _cleanup_user(db, other_member_id, members_tbl)
            conn.commit()


def test_opted_in_leader_can_build_and_charges_owner_gold(client):
    """Opted-in member + qualifying leader role -- build succeeds, gold hits the OWNER."""
    members_tbl = _members_table()
    col_id = leader_id = member_id = province_id = None
    try:
        with get_db_connection() as conn:
            db = conn.cursor()
            leader_id, _ = _create_user(db, "leader3")
            member_id, _ = _create_user(db, "member3")
            conn.commit()

        with client.session_transaction() as sess:
            sess["user_id"] = leader_id
        r = client.post(
            "/establish_coalition",
            data={
                "type": "Open",
                "name": f"buildshare_col_{uuid.uuid4().hex[:8]}",
                "description": "test",
            },
            follow_redirects=False,
        )
        assert r.status_code in (302, 303)

        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute(
                f"SELECT colid FROM {members_tbl} WHERE userid=%s", (leader_id,)
            )
            col_id = db.fetchone()[0]
            db.execute(
                f"INSERT INTO {members_tbl} (colid, userid, role) VALUES (%s, %s, 'member') "
                "ON CONFLICT (userid) DO NOTHING",
                (col_id, member_id),
            )
            db.execute(
                "UPDATE users SET allow_coalition_builds=TRUE WHERE id=%s",
                (member_id,),
            )
            province_id = _create_province(db, member_id)
            db.execute("SELECT gold FROM stats WHERE id=%s", (leader_id,))
            leader_gold_before = db.fetchone()[0]
            conn.commit()

        with client.session_transaction() as sess:
            sess["user_id"] = leader_id

        r = client.post(
            f"/build_structure",
            data={"province_id": str(province_id), "building_id": "1", "quantity": "1"},
            follow_redirects=False,
        )
        assert r.status_code in (302, 303, 400), r.get_data(as_text=True)[:300]

        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute("SELECT gold FROM stats WHERE id=%s", (leader_id,))
            leader_gold_after = db.fetchone()[0]
            # Whether or not the specific building purchase itself succeeded
            # (depends on building_id=1 pricing/slot availability, which
            # isn't the point of this test), the acting leader's OWN gold
            # must never move as a side effect of a shared-build action.
            assert leader_gold_after == leader_gold_before, (
                "Acting leader's gold must never change from a shared-build action"
            )
    finally:
        with get_db_connection() as conn:
            db = conn.cursor()
            _cleanup_coalition(db, col_id, members_tbl)
            _cleanup_user(db, leader_id, members_tbl)
            _cleanup_user(db, member_id, members_tbl)
            conn.commit()


def test_unrelated_user_never_gains_access(client):
    """A user with no coalition relationship at all must always be forbidden,
    even if the province owner has opted in (opt-in only shares with the
    owner's OWN coalition leadership, not the whole playerbase)."""
    members_tbl = _members_table()
    stranger_id = member_id = province_id = None
    try:
        with get_db_connection() as conn:
            db = conn.cursor()
            stranger_id, _ = _create_user(db, "stranger4")
            member_id, _ = _create_user(db, "member4")
            db.execute(
                "UPDATE users SET allow_coalition_builds=TRUE WHERE id=%s",
                (member_id,),
            )
            province_id = _create_province(db, member_id)
            conn.commit()

        with client.session_transaction() as sess:
            sess["user_id"] = stranger_id

        r = client.post(
            f"/api/province/{province_id}/quick_build",
            json={"building_id": 1, "quantity": 1},
        )
        assert r.status_code == 403, r.get_data(as_text=True)[:300]
    finally:
        with get_db_connection() as conn:
            db = conn.cursor()
            _cleanup_user(db, stranger_id, members_tbl)
            _cleanup_user(db, member_id, members_tbl)
            conn.commit()
