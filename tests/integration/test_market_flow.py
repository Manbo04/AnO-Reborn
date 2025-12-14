from market import give_resource


def test_give_resource_transfers(db_cursor):
    db = db_cursor

    # Create two users
    db.execute(
        (
            "INSERT INTO users (username,email,hash,date,auth_type) "
            "VALUES (%s,%s,%s,%s,%s) RETURNING id"
        ),
        ("givers_user", "givers@example.com", "h", "2020-01-01", "normal"),
    )
    giver = db.fetchone()[0]
    db.execute(
        (
            "INSERT INTO users (username,email,hash,date,auth_type) "
            "VALUES (%s,%s,%s,%s,%s) RETURNING id"
        ),
        ("taker_user", "taker@example.com", "h", "2020-01-01", "normal"),
    )
    taker = db.fetchone()[0]

    # Ensure giver has resources and taker has none
    db.execute(
        (
            "INSERT INTO resources (id, rations) VALUES (%s,%s) "
            "ON CONFLICT (id) DO UPDATE SET rations=%s"
        ),
        (giver, 50, 50),
    )
    db.execute(
        (
            "INSERT INTO resources (id, rations) VALUES (%s,%s) "
            "ON CONFLICT (id) DO UPDATE SET rations=%s"
        ),
        (taker, 0, 0),
    )

    # Transfer 10 rations from giver to taker
    res = give_resource(giver, taker, "rations", 10)
    assert res is True

    db.execute("SELECT rations FROM resources WHERE id=%s", (giver,))
    assert db.fetchone()[0] == 40
    db.execute("SELECT rations FROM resources WHERE id=%s", (taker,))
    assert db.fetchone()[0] == 10


def test_market_buy_offer_flow(db_cursor, client, set_session):
    db = db_cursor

    # Create seller and buyer
    db.execute(
        (
            "INSERT INTO users (username,email,hash,date,auth_type) "
            "VALUES (%s,%s,%s,%s,%s) RETURNING id"
        ),
        ("seller1", "seller1@example.com", "h", "2020-01-01", "normal"),
    )
    seller = db.fetchone()[0]
    db.execute(
        (
            "INSERT INTO users (username,email,hash,date,auth_type) "
            "VALUES (%s,%s,%s,%s,%s) RETURNING id"
        ),
        ("buyer1", "buyer1@example.com", "h", "2020-01-01", "normal"),
    )
    buyer = db.fetchone()[0]

    # Setup resources and gold
    db.execute(
        (
            "INSERT INTO resources (id, rations) VALUES (%s,%s) "
            "ON CONFLICT (id) DO UPDATE SET rations=%s"
        ),
        (seller, 100, 100),
    )
    db.execute(
        (
            "INSERT INTO stats (id, gold) VALUES (%s,%s) "
            "ON CONFLICT (id) DO UPDATE SET gold=%s"
        ),
        (buyer, 1000, 1000),
    )

    # Insert an offer: seller sells 20 rations at price 5 each
    db.execute(
        (
            "INSERT INTO offers (type, user_id, resource, amount, price) "
            "VALUES (%s,%s,%s,%s,%s) RETURNING offer_id"
        ),
        ("sell", seller, "rations", 20, 5),
    )
    offer_id = db.fetchone()[0]

    # Buyer buys 10 rations from the offer
    set_session("user_id", buyer)
    resp = client.post(
        f"/buy_offer/{offer_id}",
        data={f"amount_{offer_id}": "10"},
        follow_redirects=True,
    )
    assert resp.status_code in (200, 302)

    # Seller should have 10 less rations
    db.execute("SELECT rations FROM resources WHERE id=%s", (seller,))
    assert db.fetchone()[0] == 90

    # Buyer should have 10 rations
    db.execute("SELECT rations FROM resources WHERE id=%s", (buyer,))
    assert db.fetchone()[0] == 10

    # Verify seller received money (price 5 * 10 = 50)
    db.execute("SELECT gold FROM stats WHERE id=%s", (seller,))
    seller_gold = db.fetchone()
    assert seller_gold is not None and seller_gold[0] >= 50
