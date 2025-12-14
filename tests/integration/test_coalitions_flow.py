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
