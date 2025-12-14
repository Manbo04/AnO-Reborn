import os
import pytest
import http.cookies

from flask import request

from app import app as flask_app


def _set_session_cookie(client, app, key, value):
    """Utility to set session keys on the test client without using
    client.session_transaction() which can be brittle across Flask versions.
    """
    with app.test_request_context():
        sess = app.session_interface.open_session(app, request)
        sess[key] = value
        resp = app.response_class()
        app.session_interface.save_session(app, sess, resp)
        set_cookie = resp.headers.get("Set-Cookie")
        if not set_cookie:
            return
        cookie = http.cookies.SimpleCookie()
        cookie.load(set_cookie)
        for morsel in cookie.values():
            # Use positional signature (server_name, key, value)
            client.set_cookie("localhost", morsel.key, morsel.value)


@pytest.fixture
def client():
    with flask_app.test_client() as c:
        yield c


@pytest.fixture
def db_connection():
    """Provide a DB connection for integration tests. Tests that depend on
    an actual database are skipped by default and require the environment
    variable `RUN_DB_INTEGRATION=1` to be set.
    """
    if os.getenv("RUN_DB_INTEGRATION") != "1":
        pytest.skip(
            "DB integration tests disabled (set RUN_DB_INTEGRATION=1 to enable)"
        )

    import psycopg2

    conn = psycopg2.connect(
        database=os.getenv("PG_DATABASE"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        host=os.getenv("PG_HOST"),
        port=os.getenv("PG_PORT"),
    )
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


@pytest.fixture
def db_cursor(db_connection):
    """Yield a cursor wrapped in a transaction which will be rolled back
    after the test to avoid leaving persistent state in the test database.
    """
    cur = db_connection.cursor()
    try:
        yield cur
    finally:
        db_connection.rollback()
        cur.close()


@pytest.fixture
def set_session(client):
    def _set(key, value):
        _set_session_cookie(client, flask_app, key, value)

    return _set
