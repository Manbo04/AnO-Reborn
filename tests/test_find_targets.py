import pytest
from app import app
from database import get_db_connection


def make_user(db, username):
    db.execute(
        "INSERT INTO users (username, email, hash, date, auth_type) VALUES (%s,%s,%s,%s,%s)",
        (username, f"{username}@example.com", "h", "2020-01-01", "normal"),
    )
    db.execute("SELECT id FROM users WHERE username=%s", (username,))
    row = db.fetchone()
    return row[0] if row else None


def test_find_targets_get_no_targets():
    with app.test_client() as client:
        with get_db_connection() as conn:
            db = conn.cursor()
            # create a user for the requester and ensure no other users exist matching filters
            db.execute("DELETE FROM users WHERE username LIKE 'ft_test_%'")
            db.execute(
                "DELETE FROM provinces WHERE userId IN (SELECT id FROM users WHERE username LIKE 'ft_test_%')"
            )
            db.execute(
                "DELETE FROM military WHERE id IN (SELECT id FROM users WHERE username LIKE 'ft_test_%')"
            )
            conn.commit()
            uid = make_user(db, "ft_test_requester")
            conn.commit()
        with client.session_transaction() as sess:
            sess["user_id"] = uid
        resp = client.get("/find_targets")
        assert resp.status_code == 200
        assert b"Potential War Targets" in resp.data


def test_find_targets_shows_target():
    with app.test_client() as client:
        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute("DELETE FROM users WHERE username LIKE 'ft_test_%'")
            conn.commit()
            requester = make_user(db, "ft_test_requester")
            target = make_user(db, "ft_test_target")
            # give target a province and some military
            db.execute(
                "INSERT INTO provinces (userId, cityCount, land) VALUES (%s, %s, %s)",
                (target, 1, 10),
            )
            db.execute(
                "INSERT INTO military (id, soldiers, artillery) VALUES (%s, %s, %s) ON CONFLICT (id) DO UPDATE SET soldiers=%s, artillery=%s",
                (target, 100, 5, 100, 5),
            )
            conn.commit()
        with client.session_transaction() as sess:
            sess["user_id"] = requester
        resp = client.get("/find_targets")
        assert resp.status_code == 200
        assert b"ft_test_target" in resp.data
