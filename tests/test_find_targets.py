from app import app
from database import get_db_connection
from tests._db_cleanup import purge_users_where


def make_user(db, username):
    db.execute(
        "INSERT INTO users (username, email, hash, date, auth_type) VALUES (%s,%s,%s,%s,%s)",
        (username, f"{username}@example.com", "h", "2020-01-01", "normal"),
    )
    db.execute("SELECT id FROM users WHERE username=%s", (username,))
    return db.fetchone()[0]


def test_find_targets_get_no_targets():
    with app.test_client() as client:
        with get_db_connection() as conn:
            db = conn.cursor()
            # create a user for the requester and ensure no other users exist matching filters
            purge_users_where(db, "username LIKE 'ft_test_%'", ())
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
            purge_users_where(db, "username LIKE 'ft_test_%'", ())
            conn.commit()
            requester = make_user(db, "ft_test_requester")
            target = make_user(db, "ft_test_target")
            # Same province + army for both, so the target sits inside the
            # requester's influence bracket (0.9x-2x; a 0-influence nation
            # only sees targets up to 100 influence).
            for uid, label in ((requester, "ft requester"), (target, "ft target")):
                db.execute(
                    "INSERT INTO provinces (userId, provinceName, cityCount, land) VALUES (%s, %s, %s, %s)",
                    (uid, label, 1, 10),
                )
                db.execute(
                    "INSERT INTO military (id, soldiers, artillery) VALUES (%s, %s, %s) ON CONFLICT (id) DO UPDATE SET soldiers=%s, artillery=%s",
                    (uid, 100, 5, 100, 5),
                )
            conn.commit()
        with client.session_transaction() as sess:
            sess["user_id"] = requester
        resp = client.get("/find_targets")
        assert resp.status_code == 200
        assert b"ft_test_target" in resp.data


def test_find_targets_not_crowded_out_by_out_of_range_nations():
    """Regression (2026-10-06): the influence bracket was applied in Python
    AFTER "ORDER BY username LIMIT 50". With 233 of 289 live nations in the
    0-1 province band, only the first 50 names were ever considered, so
    in-range targets later in the alphabet never showed up."""
    with app.test_client() as client:
        with get_db_connection() as conn:
            db = conn.cursor()
            purge_users_where(db, "username LIKE 'ft_crowd_%'", ())
            conn.commit()
            requester = make_user(db, "ft_crowd_requester")
            target = make_user(db, "ft_crowd_zzz_target")  # sorts last
            for uid, label in ((requester, "crowd requester"), (target, "crowd target")):
                db.execute(
                    "INSERT INTO provinces (userId, provinceName, cityCount, land) VALUES (%s, %s, %s, %s)",
                    (uid, label, 1, 10),
                )
                db.execute(
                    "INSERT INTO military (id, soldiers, artillery) VALUES (%s, %s, %s) "
                    "ON CONFLICT (id) DO UPDATE SET soldiers=%s, artillery=%s",
                    (uid, 100, 5, 100, 5),
                )
            # 55 zero-influence nations in the same province band, sorting first.
            for i in range(55):
                make_user(db, f"ft_crowd_aaa_{i:02d}")
            conn.commit()
        try:
            with client.session_transaction() as sess:
                sess["user_id"] = requester
            resp = client.get("/find_targets")
            assert resp.status_code == 200
            assert b"ft_crowd_zzz_target" in resp.data
        finally:
            with get_db_connection() as conn:
                db = conn.cursor()
                db.execute(
                    "DELETE FROM provinces WHERE userid IN "
                    "(SELECT id FROM users WHERE username LIKE 'ft_crowd_%')"
                )
                purge_users_where(db, "username LIKE 'ft_crowd_%'", ())
                conn.commit()

