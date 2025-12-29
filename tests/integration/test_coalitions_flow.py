import time


def make_or_get_user(db, username, email):
    db.execute("SELECT id FROM users WHERE username=%s OR email=%s", (username, email))
    row = db.fetchone()
    if row:
        return row[0]
    db.execute(
        (
            "INSERT INTO users (username,email,hash,date,auth_type) "
            "VALUES (%s,%s,%s,%s,%s)"
        ),
        (username, email, "h", "2020-01-01", "normal"),
    )
    db.execute("SELECT id FROM users WHERE username=%s", (username,))
    return db.fetchone()[0]


def test_coalition_establish_and_bank_request(db_cursor, client, set_session):
    # This is a DB-integration test (skipped by default). It verifies
    # establishing a coalition and creating a bank request.
    db = db_cursor

    # Create a leader user and log them in
    leader = make_or_get_user(
        db, f"coal_leader_{int(time.time())}", "leader@example.com"
    )

    set_session("user_id", leader)

    # Establish coalition via route
    resp = client.post(
        "/establish_coalition",
        data={"type": "Open", "name": f"coal_{leader}", "description": "Integration"},
        follow_redirects=True,
    )
    assert resp.status_code in (200, 302)

    # Verify coalition exists
    db.execute("SELECT id FROM colNames WHERE name LIKE %s", (f"coal_{leader}",))
    row = db.fetchone()
    assert row is not None
    col_id = row[0]

    # Create a bank request as leader
    resp = client.post(
        "/col_request_bank",
        data={"amount": "10", "resource": "money", "colId": str(col_id)},
        follow_redirects=True,
    )
    assert resp.status_code in (200, 302)

    # Changes are rolled back by `db_cursor` fixture; no cleanup required.


def test_treaty_offer_accept_and_break(db_cursor, client, set_session):
    db = db_cursor

    leader_a = make_or_get_user(
        db, f"treaty_leader_a_{int(time.time())}", "a_coal@example.com"
    )
    leader_b = make_or_get_user(
        db, f"treaty_leader_b_{int(time.time())}", "b_coal@example.com"
    )

    # Create coalition records
    db.execute(
        (
            "INSERT INTO colNames (name, type, description, date) "
            "VALUES (%s,%s,%s,%s) RETURNING id"
        ),
        (f"coal_a_{leader_a}", "Open", "desc", "2020-01-01"),
    )
    col_a = db.fetchone()[0]
    db.execute(
        (
            "INSERT INTO colNames (name, type, description, date) "
            "VALUES (%s,%s,%s,%s) RETURNING id"
        ),
        (f"coal_b_{leader_b}", "Open", "desc", "2020-01-01"),
    )
    col_b = db.fetchone()[0]

    # Add leaders to coalitions
    db.execute(
        "INSERT INTO coalitions (userId, colId, role) VALUES (%s,%s,%s)",
        (leader_a, col_a, "leader"),
    )
    db.execute(
        "INSERT INTO coalitions (userId, colId, role) VALUES (%s,%s,%s)",
        (leader_b, col_b, "leader"),
    )

    # Leader A offers a treaty to coalition B
    set_session("user_id", leader_a)
    resp = client.post(
        "/offer_treaty",
        data={
            "coalition_name": f"coal_b_{leader_b}",
            "treaty_name": "Alliance",
            "treaty_message": "We like you",
        },
        follow_redirects=True,
    )
    assert resp.status_code in (200, 302)

    # Verify treaty exists and is pending
    db.execute(
        "SELECT id, status FROM treaties WHERE col1_id=%s AND col2_id=%s",
        (col_a, col_b),
    )
    row = db.fetchone()
    assert row is not None
    offer_id, status = row
    assert status == "Pending"

    # Leader B accepts the treaty
    set_session("user_id", leader_b)
    resp = client.post(f"/accept_treaty/{offer_id}", follow_redirects=True)
    assert resp.status_code in (200, 302)

    db.execute("SELECT status FROM treaties WHERE id=%s", (offer_id,))
    assert db.fetchone()[0] == "Active"

    # Leader A breaks the treaty
    set_session("user_id", leader_a)
    resp = client.post(f"/break_treaty/{offer_id}", follow_redirects=True)
    assert resp.status_code in (200, 302)

    db.execute("SELECT id FROM treaties WHERE id=%s", (offer_id,))
    assert db.fetchone() is None


def test_accept_bank_request_withdraws_resources(db_cursor, client, set_session):
    db = db_cursor

    leader = make_or_get_user(
        db, f"bank_leader_{int(time.time())}", "leader_bank@example.com"
    )
    member = make_or_get_user(
        db, f"bank_member_{int(time.time())}", "member_bank@example.com"
    )

    # Create coalition and add both users
    db.execute(
        (
            "INSERT INTO colNames (name, type, description, date) "
            "VALUES (%s,%s,%s,%s) RETURNING id"
        ),
        (f"coal_bank_{leader}", "Open", "desc", "2020-01-01"),
    )
    col_id = db.fetchone()[0]
    db.execute(
        "INSERT INTO coalitions (userId, colId, role) VALUES (%s,%s,%s)",
        (leader, col_id, "leader"),
    )
    db.execute(
        "INSERT INTO coalitions (userId, colId, role) VALUES (%s,%s,%s)",
        (member, col_id, "member"),
    )

    # Initialize bank funds (upsert)
    db.execute(
        (
            "INSERT INTO colBanks (colId, money) VALUES (%s,%s) "
            "ON CONFLICT (colId) DO UPDATE SET money=%s"
        ),
        (col_id, 1000, 1000),
    )

    # Ensure member has a stats row
    db.execute(
        (
            "INSERT INTO stats (id, gold) VALUES (%s, %s) "
            "ON CONFLICT (id) DO UPDATE SET gold=%s"
        ),
        (member, 0, 0),
    )

    # Insert a bank request: member requests 100 money
    db.execute(
        (
            "INSERT INTO colBanksRequests (reqId, colId, amount, resource) "
            "VALUES (%s,%s,%s,%s) RETURNING id"
        ),
        (member, col_id, 100, "money"),
    )
    bank_req_id = db.fetchone()[0]

    # Leader accepts the bank request
    set_session("user_id", leader)
    resp = client.post(f"/accept_bank_request/{bank_req_id}", follow_redirects=True)
    assert resp.status_code in (200, 302)

    # Member should have received 100 gold
    db.execute("SELECT gold FROM stats WHERE id=%s", (member,))
    row = db.fetchone()
    member_gold = row[0] if row else 0
    assert member_gold >= 100

    # Bank should have decreased by 100
    db.execute("SELECT money FROM colBanks WHERE colId=%s", (col_id,))
    assert db.fetchone()[0] == 900
