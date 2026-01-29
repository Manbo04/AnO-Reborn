from app import app
from database import get_db_connection


def make_user(db, username):
    db.execute(
        "INSERT INTO users (username, email, hash, date, auth_type) "
        "VALUES (%s,%s,%s,%s,%s) RETURNING id",
        (username, f"{username}@example.com", "h", "2020-01-01", "normal"),
    )
    uid = db.fetchone()
    if uid:
        return uid[0]
    db.execute("SELECT id FROM users WHERE username=%s", (username,))
    return db.fetchone()[0]


def ensure_stats(db, uid):
    db.execute(
        "INSERT INTO stats (id, gold, location) "
        "VALUES (%s, %s, %s) ON CONFLICT (id) DO NOTHING",
        (uid, 0, ""),
    )
    # Ensure minimal military record to avoid None fetches in country view
    db.execute(
        "INSERT INTO military (id, spies) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING",
        (uid, 0),
    )


def test_country_shows_theoretical_and_projected(monkeypatch):
    import countries

    # Prepare DB user
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("DELETE FROM users WHERE username=%s", ("ui_revenue_test",))
        conn.commit()
        uid = make_user(db, "ui_revenue_test")
        ensure_stats(db, uid)
        conn.commit()

    # Fake revenue that distinguishes theoretical vs projected
    from variables import RESOURCES

    revenue = {"gross": {}, "gross_theoretical": {}, "net": {}}
    # initialize all resources to zero to match template expectations
    for r in RESOURCES + ["money", "energy"]:
        revenue["gross"][r] = 0
        revenue["gross_theoretical"][r] = 0
        revenue["net"][r] = 0

    # set a focused example
    revenue["gross"]["lumber"] = 77
    revenue["gross_theoretical"]["lumber"] = 140
    revenue["net"]["lumber"] = 77

    monkeypatch.setattr(countries, "get_revenue", lambda cid: revenue)

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user_id"] = uid

        resp = client.get(f"/country/id={uid}")
        assert resp.status_code == 200
        data = resp.data.decode("utf-8")

        # Theoretical (original) number should be displayed
        assert "140" in data
        # Projected small label with tooltip should be present
        assert "Projected: 77" in data or "Projected: 77" in resp.get_data(as_text=True)
        assert "Projected (applies productivity & rounding): 77" in data


def test_country_handles_missing_gross_theoretical(monkeypatch):
    import countries

    # Prepare DB user
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("DELETE FROM users WHERE username=%s", ("ui_revenue_test2",))
        conn.commit()
        uid = make_user(db, "ui_revenue_test2")
        ensure_stats(db, uid)
        conn.commit()

    # Simulate get_revenue returning no 'gross_theoretical' key
    def minimal_revenue(cid):
        return {"gross": {"lumber": 10}, "net": {"lumber": 10}}

    monkeypatch.setattr(countries, "get_revenue", minimal_revenue)

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user_id"] = uid

        resp = client.get(f"/country/id={uid}")
        # Should not 500 even if gross_theoretical missing
        assert resp.status_code == 200
