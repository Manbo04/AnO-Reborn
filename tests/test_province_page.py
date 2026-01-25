from database import get_db_cursor
from app import app


def test_province_page_accessible():
    import uuid

    # Create user and province, then request province page as that user (use unique username)
    with get_db_cursor() as db:
        username = f"p_{uuid.uuid4().hex[:8]}"
        email = f"{username}@example.com"
        db.execute(
            "INSERT INTO users (username, email, hash, date, auth_type) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (username, email, "h", "2020-01-01", "n"),
        )
        user_id = db.fetchone()[0]
        # create basic stats/resources rows
        db.execute(
            "INSERT INTO stats (id, location) VALUES (%s, %s)", (user_id, "testloc")
        )
        db.execute("INSERT INTO resources (id, rations) VALUES (%s, %s)", (user_id, 10))
        # create province
        db.execute(
            "INSERT INTO provinces (userid, provincename, population, pollution, happiness, productivity, consumer_spending, citycount, land, energy) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (user_id, "TestProv", 1000, 0, 50, 50, 100, 2, 10, 5),
        )
        p_id = db.fetchone()[0]

    # Use Flask test client and set session
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user_id"] = user_id

        resp = client.get(f"/province/{p_id}")
        assert resp.status_code == 200
        assert b"TestProv" in resp.data
