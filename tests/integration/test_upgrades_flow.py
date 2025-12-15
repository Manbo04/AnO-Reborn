def test_get_upgrades_and_buy(db_cursor, client, set_session):
    db = db_cursor

    # Create test user
    db.execute(
        (
            "INSERT INTO users (username,email,hash,date,auth_type) "
            "VALUES (%s,%s,%s,%s,%s) RETURNING id"
        ),
        ("upg_user", "upg@example.com", "h", "2020-01-01", "normal"),
    )
    uid = db.fetchone()[0]

    # Ensure stats/resources/upgrades rows exist
    db.execute(
        (
            "INSERT INTO stats (id, gold) VALUES (%s,%s) "
            "ON CONFLICT (id) DO UPDATE SET gold=%s"
        ),
        (uid, 1000000000, 1000000000),
    )
    db.execute(
        "INSERT INTO resources (id) VALUES (%s) ON CONFLICT (id) DO NOTHING", (uid,)
    )
    db.execute(
        "INSERT INTO upgrades (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING",
        (uid,),
    )

    set_session("user_id", uid)

    # Get upgrades page
    resp = client.get("/upgrades")
    assert resp.status_code == 200

    # Try buying a cheap upgrade (use a known key from upgrades.py prices)
    resp = client.post("/upgrades_sb/buy/strongerexplosives", follow_redirects=True)
    assert resp.status_code in (200, 302)

    # Verify upgrade was applied
    db.execute("SELECT strongerexplosives FROM upgrades WHERE user_id=%s", (uid,))
    val = db.fetchone()[0]
    assert val == 1
