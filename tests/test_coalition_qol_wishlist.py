"""Coalition QOL wishlist (luciuskonst, suggestions forum, 2026-09-26):

1. leaders can make Share Build Access the coalition default
2. accountable banking: officers withdraw via requests, optional no-self-approve
3. coalitions can rename their roles
4. bank log and tax log are separate, with a full paginated log
5. CSV export of the logs
6. leaders control which roles see which coalition information

Every row these tests create is removed in `finally` (this machine's shell can
point at prod -- run with `env -u DATABASE_PUBLIC_URL DATABASE_URL=<local>`).
"""

import os
import uuid

import pytest

from database import get_coalition_members_table, get_db_connection

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_PUBLIC_URL") and not os.getenv("DATABASE_URL"),
    reason="Requires Postgres (DATABASE_PUBLIC_URL or DATABASE_URL)",
)


@pytest.fixture(autouse=True)
def _render_v2_coalition_page(monkeypatch):
    # Production renders coalition_v2.html (THEME_V2_PAGES includes "coalition").
    monkeypatch.setenv("THEME_V2_PAGES", "coalition")


def _members_table():
    return get_coalition_members_table() or "coalitions_legacy"


def _create_user(db, suffix, gold=5_000_000):
    name = f"colqol_{suffix}_{uuid.uuid4().hex[:8]}"
    db.execute(
        "INSERT INTO users (username, email, date, hash, auth_type) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (name, f"{name}@example.test", "2026-09-26", "", "normal"),
    )
    uid = db.fetchone()[0]
    db.execute(
        "INSERT INTO stats (id, location, gold) VALUES (%s, %s, %s) "
        "ON CONFLICT (id) DO UPDATE SET gold = %s",
        (uid, "Grassland", gold, gold),
    )
    return uid, name


def _login(client, uid):
    with client.session_transaction() as sess:
        sess["user_id"] = uid


@pytest.fixture
def coalition(client):
    """Leader + banker + deputy + two plain members in a fresh coalition,
    bank seeded with 1,000,000 gold."""
    members_tbl = _members_table()
    ids = {}
    col_id = None
    try:
        with get_db_connection() as conn:
            db = conn.cursor()
            for key in ("leader", "banker", "deputy", "member", "member2"):
                ids[key], ids[f"{key}_name"] = _create_user(db, key)
            conn.commit()

        _login(client, ids["leader"])
        r = client.post(
            "/establish_coalition",
            data={
                "type": "Open",
                "name": f"colqol_{uuid.uuid4().hex[:8]}",
                "description": "test",
            },
        )
        assert r.status_code in (302, 303)

        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute(f"SELECT colid FROM {members_tbl} WHERE userid=%s", (ids["leader"],))
            col_id = db.fetchone()[0]
            for key, role in (
                ("banker", "banker"),
                ("deputy", "deputy_leader"),
                ("member", "member"),
                ("member2", "member"),
            ):
                db.execute(
                    f"INSERT INTO {members_tbl} (colid, userid, role) VALUES (%s, %s, %s) "
                    "ON CONFLICT (userid) DO NOTHING",
                    (col_id, ids[key], role),
                )
            db.execute("UPDATE colBanks SET money = 1000000 WHERE colId = %s", (col_id,))
            conn.commit()

        ids["col_id"] = col_id
        yield ids
    finally:
        user_ids = [v for k, v in ids.items() if not k.endswith("_name") and k != "col_id"]
        with get_db_connection() as conn:
            db = conn.cursor()
            if col_id:
                db.execute("DELETE FROM col_bank_transactions WHERE coalition_id=%s", (col_id,))
                db.execute("DELETE FROM col_bank_contributions WHERE coalition_id=%s", (col_id,))
                db.execute("DELETE FROM col_role_names WHERE coalition_id=%s", (col_id,))
                db.execute("DELETE FROM colBanksRequests WHERE colId=%s", (col_id,))
                db.execute("DELETE FROM colBanks WHERE colId=%s", (col_id,))
                db.execute(f"DELETE FROM {members_tbl} WHERE colid=%s", (col_id,))
                db.execute("DELETE FROM colNames WHERE id=%s", (col_id,))
            for uid in user_ids:
                db.execute("DELETE FROM news WHERE destination_id=%s", (uid,))
                db.execute("DELETE FROM user_economy WHERE user_id=%s", (uid,))
                db.execute("DELETE FROM provinces WHERE userId=%s", (uid,))
                db.execute("DELETE FROM colBanksRequests WHERE reqId=%s", (uid,))
                db.execute(f"DELETE FROM {members_tbl} WHERE userid=%s", (uid,))
                db.execute("DELETE FROM referral_active_days WHERE referred_user_id=%s", (uid,))
                db.execute("DELETE FROM stats WHERE id=%s", (uid,))
                db.execute("DELETE FROM users WHERE id=%s", (uid,))
            conn.commit()


def _q(sql, params=()):
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(sql, params)
        try:
            return db.fetchall()
        finally:
            conn.commit()


def _exec(sql, params=()):
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(sql, params)
        conn.commit()


def _save_settings(client, col_id, **overrides):
    data = {"bank_self_approve": "on"}
    data.update(overrides)
    return client.post(f"/coalition/{col_id}/settings", data=data)


# ---- 1. share build access default -------------------------------------

def test_share_default_applies_only_to_members_who_never_chose(client, coalition):
    from app_core.coalitions.repositories import member_shares_with_coalition

    c = coalition
    # member2 explicitly opted OUT via the toggle.
    _login(client, c["member2"])
    client.post("/coalition/build-sharing", data={})

    with get_db_connection() as conn:
        db = conn.cursor()
        assert member_shares_with_coalition(db, c["member"]) is False

    _login(client, c["leader"])
    r = _save_settings(client, c["col_id"], share_builds_default="on")
    assert r.status_code in (302, 303)

    with get_db_connection() as conn:
        db = conn.cursor()
        assert member_shares_with_coalition(db, c["member"]) is True
        # explicit opt-out wins over the coalition default
        assert member_shares_with_coalition(db, c["member2"]) is False

    # member (never chose) was told; member2 (chose) and the leader were not.
    news = {r[0] for r in _q(
        "SELECT destination_id FROM news WHERE destination_id = ANY(%s) "
        "AND message LIKE %s",
        ([c["member"], c["member2"], c["leader"]], "%Share Build Access%"),
    )}
    assert news == {c["member"]}


def test_non_leader_cannot_change_settings_or_role_names(client, coalition):
    c = coalition
    _login(client, c["deputy"])
    r = _save_settings(client, c["col_id"], bank_require_requests="on")
    assert r.status_code == 400
    r = client.post(f"/coalition/{c['col_id']}/role_names", data={"role_banker": "Treasurer"})
    assert r.status_code == 400
    assert _q("SELECT bank_require_requests FROM colNames WHERE id=%s", (c["col_id"],))[0][0] is False
    assert _q("SELECT count(*) FROM col_role_names WHERE coalition_id=%s", (c["col_id"],))[0][0] == 0


# ---- 2. accountable banking ---------------------------------------------

def test_request_mode_blocks_direct_withdraw_and_self_approve(client, coalition):
    c = coalition
    _login(client, c["leader"])
    _save_settings(client, c["col_id"], bank_require_requests="on", bank_self_approve="")
    # _save_settings always sends bank_self_approve; an empty value is "off".
    assert _q(
        "SELECT bank_require_requests, bank_self_approve FROM colNames WHERE id=%s",
        (c["col_id"],),
    )[0] == (True, False)

    # Banker's direct withdrawal is refused, bank untouched.
    _login(client, c["banker"])
    client.post(f"/withdraw_from_bank/{c['col_id']}", data={"money": "1000"})
    assert _q("SELECT money FROM colBanks WHERE colId=%s", (c["col_id"],))[0][0] == 1_000_000

    # Banker files a request and can't approve it themselves.
    client.post(f"/request_from_bank/{c['col_id']}", data={"money": "1000"})
    req_id = _q(
        "SELECT id FROM colBanksRequests WHERE colId=%s AND reqId=%s",
        (c["col_id"], c["banker"]),
    )[0][0]
    client.post(f"/accept_bank_request/{req_id}")
    assert _q("SELECT count(*) FROM colBanksRequests WHERE id=%s", (req_id,))[0][0] == 1
    assert _q("SELECT money FROM colBanks WHERE colId=%s", (c["col_id"],))[0][0] == 1_000_000

    # Deputy approves it: money moves, log records the deputy as actor.
    _login(client, c["deputy"])
    client.post(f"/accept_bank_request/{req_id}")
    assert _q("SELECT money FROM colBanks WHERE colId=%s", (c["col_id"],))[0][0] == 999_000
    assert _q(
        "SELECT user_id, actor_id, direction FROM col_bank_transactions "
        "WHERE coalition_id=%s AND resource='money'",
        (c["col_id"],),
    ) == [(c["banker"], c["deputy"], "withdraw")]


def test_self_approve_allowed_by_default(client, coalition):
    c = coalition
    _login(client, c["banker"])
    client.post(f"/request_from_bank/{c['col_id']}", data={"money": "500"})
    req_id = _q("SELECT id FROM colBanksRequests WHERE reqId=%s", (c["banker"],))[0][0]
    client.post(f"/accept_bank_request/{req_id}")
    assert _q("SELECT money FROM colBanks WHERE colId=%s", (c["col_id"],))[0][0] == 999_500


def test_member_can_cancel_own_request_but_not_others(client, coalition):
    c = coalition
    _login(client, c["member"])
    client.post(f"/request_from_bank/{c['col_id']}", data={"money": "10"})
    _login(client, c["member2"])
    client.post(f"/request_from_bank/{c['col_id']}", data={"money": "20"})
    own = _q("SELECT id FROM colBanksRequests WHERE reqId=%s", (c["member"],))[0][0]
    other = _q("SELECT id FROM colBanksRequests WHERE reqId=%s", (c["member2"],))[0][0]

    _login(client, c["member"])
    r = client.post(f"/remove_bank_request/{other}")
    assert r.status_code == 400
    client.post(f"/remove_bank_request/{own}")
    remaining = {r[0] for r in _q(
        "SELECT id FROM colBanksRequests WHERE colId=%s", (c["col_id"],)
    )}
    assert remaining == {other}


# ---- 3. role names ------------------------------------------------------

def test_leader_renames_roles_and_page_shows_them(client, coalition):
    c = coalition
    _login(client, c["leader"])
    r = client.post(
        f"/coalition/{c['col_id']}/role_names",
        data={
            "role_banker": "  Royal   Treasurer ",
            "role_member": "<b>Citizen</b>",
            "role_general": "",
            "role_leader": "Leader",  # same as default -> not stored
        },
    )
    assert r.status_code in (302, 303)
    stored = dict(_q(
        "SELECT role, display_name FROM col_role_names WHERE coalition_id=%s",
        (c["col_id"],),
    ))
    assert stored == {"banker": "Royal Treasurer", "member": "<b>Citizen</b>"}

    page = client.get(f"/coalition/{c['col_id']}").get_data(as_text=True)
    assert "Royal Treasurer" in page
    assert "&lt;b&gt;Citizen&lt;/b&gt;" in page and "<b>Citizen</b>" not in page


# ---- 4/5. separate logs, full log, CSV ------------------------------------

def _seed_log(c):
    rows = [
        (c["col_id"], c["member"], c["member"], "money", 100, "deposit"),
        (c["col_id"], c["member2"], c["member2"], "steel", 5, "deposit"),
        (c["col_id"], c["member"], c["member"], "tax", 7, "deposit"),
    ]
    with get_db_connection() as conn:
        db = conn.cursor()
        db.executemany(
            "INSERT INTO col_bank_transactions "
            "(coalition_id, user_id, actor_id, resource, amount, direction) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            rows,
        )
        conn.commit()


def test_bank_and_tax_logs_are_separate(client, coalition):
    c = coalition
    _seed_log(c)
    _login(client, c["banker"])
    body = client.get(f"/coalition/{c['col_id']}/bank_log.csv?kind=bank").get_data(as_text=True)
    lines = body.strip().splitlines()
    assert lines[0].startswith("time_utc,type,member")
    assert len(lines) == 3  # header + 2 bank rows, no tax row
    assert ",tax," not in body

    tax = client.get(f"/coalition/{c['col_id']}/bank_log.csv?kind=tax").get_data(as_text=True)
    tax_lines = tax.strip().splitlines()
    assert len(tax_lines) == 2 and tax_lines[1].split(",")[1] == "tax"

    r = client.get(f"/coalition/{c['col_id']}/bank_log?kind=bank")
    assert r.status_code == 200
    assert c["member2_name"] in r.get_data(as_text=True)


def test_plain_member_sees_only_own_rows_and_no_tax_log(client, coalition):
    c = coalition
    _seed_log(c)
    _login(client, c["member2"])
    body = client.get(f"/coalition/{c['col_id']}/bank_log.csv?kind=bank").get_data(as_text=True)
    assert c["member2_name"] in body and c["member_name"] not in body
    assert client.get(f"/coalition/{c['col_id']}/bank_log.csv?kind=tax").status_code == 403


def test_outsider_cannot_read_logs(client, coalition):
    c = coalition
    with get_db_connection() as conn:
        db = conn.cursor()
        outsider, _ = _create_user(db, "outsider")
        conn.commit()
    try:
        _login(client, outsider)
        assert client.get(f"/coalition/{c['col_id']}/bank_log.csv").status_code == 400
        assert client.get(f"/coalition/{c['col_id']}/bank_log").status_code == 400
    finally:
        _exec("DELETE FROM stats WHERE id=%s", (outsider,))
        _exec("DELETE FROM users WHERE id=%s", (outsider,))


def test_csv_neutralises_formula_usernames():
    from app_core.coalitions.routes import _csv_safe

    assert _csv_safe("=HYPERLINK(1)") == "'=HYPERLINK(1)"
    assert _csv_safe("@cmd") == "'@cmd"
    assert _csv_safe("Dede") == "Dede"
    assert _csv_safe(None) == ""


# ---- 6. visibility settings ---------------------------------------------

def test_visibility_matrix_controls_logs_and_balances(client, coalition):
    c = coalition
    _seed_log(c)
    _login(client, c["leader"])
    # Give plain members the full bank log; take bank balances away from them.
    _save_settings(
        client,
        c["col_id"],
        access_bank_logs=["banker", "member"],
        access_bank_balances=["banker"],
    )
    _login(client, c["member2"])
    body = client.get(f"/coalition/{c['col_id']}/bank_log.csv?kind=bank").get_data(as_text=True)
    assert c["member_name"] in body

    page = client.get(f"/coalition/{c['col_id']}").get_data(as_text=True)
    assert "1,000,000" not in page

    # Deputy was dropped from bank_logs -> sees only own rows now.
    _login(client, c["deputy"])
    body = client.get(f"/coalition/{c['col_id']}/bank_log.csv?kind=bank").get_data(as_text=True)
    assert c["member_name"] not in body


def test_member_revenue_requires_sharing_and_allowed_role(client, coalition):
    c = coalition
    url = f"/coalition/{c['col_id']}/member/{c['member']}/revenue"

    _login(client, c["leader"])
    assert client.get(url).status_code == 403  # member not sharing

    _login(client, c["member"])
    client.post("/coalition/build-sharing", data={"enabled": "on"})

    _login(client, c["leader"])
    assert client.get(url).status_code == 200

    # banker isn't in member_revenue by default
    _login(client, c["banker"])
    assert client.get(url).status_code == 403

    # a member of another coalition / outsider can't use a guessed URL
    _login(client, c["member2"])
    assert client.get(url).status_code == 403


def test_province_builds_role_follows_settings(client, coalition):
    from app_core.coalitions.repositories import can_manage_province_builds

    c = coalition
    _login(client, c["member"])
    client.post("/coalition/build-sharing", data={"enabled": "on"})

    with get_db_connection() as conn:
        db = conn.cursor()
        assert can_manage_province_builds(db, c["banker"], c["member"]) is True
        assert can_manage_province_builds(db, c["member2"], c["member"]) is False

    _login(client, c["leader"])
    _save_settings(client, c["col_id"], access_province_builds=["member"])

    with get_db_connection() as conn:
        db = conn.cursor()
        assert can_manage_province_builds(db, c["banker"], c["member"]) is False
        assert can_manage_province_builds(db, c["member2"], c["member"]) is True
        assert can_manage_province_builds(db, c["leader"], c["member"]) is True
