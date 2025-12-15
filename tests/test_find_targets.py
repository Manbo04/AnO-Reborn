# pytest not required at module level; remove unused import to satisfy linter
from app import app
from database import get_db_connection


def make_user(db, username):
    db.execute(
        (
            "INSERT INTO users (username, email, hash, date, auth_type) "
            "VALUES (%s,%s,%s,%s,%s)"
        ),
        (username, f"{username}@example.com", "h", "2020-01-01", "normal"),
    )
    db.execute("SELECT id FROM users WHERE username=%s", (username,))
    return db.fetchone()[0]


def test_find_targets_get_no_targets():
    with app.test_client() as client:
        with get_db_connection() as conn:
            db = conn.cursor()
            # create a user for the requester and ensure no other users exist
            # matching filters
            db.execute("DELETE FROM users WHERE username LIKE 'ft_test_%'")
            db.execute(
                (
                    "DELETE FROM provinces WHERE userId IN (SELECT id FROM users "
                    "WHERE username LIKE 'ft_test_%')"
                )
            )
            db.execute(
                (
                    "DELETE FROM military WHERE id IN (SELECT id FROM users "
                    "WHERE username LIKE 'ft_test_%')"
                )
            )
            conn.commit()
            uid = make_user(db, "ft_test_requester")
            conn.commit()
        # Set the session cookie directly instead of using
        # client.session_transaction() which may not be available in
        # certain test environments.
        import http.cookies

        from flask import request

        with app.test_request_context():
            sess = app.session_interface.open_session(app, request)
            sess["user_id"] = uid
            resp = app.response_class()
            app.session_interface.save_session(app, sess, resp)
            set_cookie = resp.headers.get("Set-Cookie")
            cookie = http.cookies.SimpleCookie()
            cookie.load(set_cookie)
            for morsel in cookie.values():
                client.set_cookie("localhost", morsel.key, morsel.value)
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
                (
                    "INSERT INTO military (id, soldiers, artillery) "
                    "VALUES (%s, %s, %s) ON CONFLICT (id) DO UPDATE "
                    "SET soldiers=%s, artillery=%s"
                ),
                (target, 100, 5, 100, 5),
            )
            conn.commit()
        import http.cookies

        from flask import request

        with app.test_request_context():
            sess = app.session_interface.open_session(app, request)
            sess["user_id"] = requester
            resp = app.response_class()
            app.session_interface.save_session(app, sess, resp)
            set_cookie = resp.headers.get("Set-Cookie")
            cookie = http.cookies.SimpleCookie()
            cookie.load(set_cookie)
            for morsel in cookie.values():
                client.set_cookie("localhost", morsel.key, morsel.value)
        resp = client.get("/find_targets")
        assert resp.status_code == 200
        assert b"ft_test_target" in resp.data
