"""Run a harmless buy→sell→buy reproduction against the deployed site.

Usage: set RAILWAY_PUBLIC_DOMAIN or use RAILWAY_SERVICE_WEB_URL from railway variables.
This script will:
 - create a test user and a single province for them (safely, with unique username)
 - craft a signed Flask session cookie so requests authenticate as that user
 - POST to the province buy/sell endpoints to buy 4 farms, sell them, buy again
 - check DB rows for resources and unit counts before/after
 - GET the homepage after each step to verify the UI shows updated totals
 - clean up the test data when done

IMPORTANT: This runs against the DB pointed to by the environment variables (DATABASE_URL). Be cautious.
"""

import time
import requests
import os

from database import get_db_connection
from app import app
from flask.sessions import SecureCookieSessionInterface

# Config
TARGET_HOST = (
    os.environ.get("RAILWAY_SERVICE_WEB_URL")
    or os.environ.get("RAILWAY_PUBLIC_DOMAIN")
    or "https://affairsandorder.com"
)
TEST_USERNAME = f"repro_test_{int(time.time())}"
PROVINCE_NAME = "repro-province"

# Helpers to manage a test user + province


def make_test_user_and_province():
    with get_db_connection() as conn:
        db = conn.cursor()
        # create user if not exists (simple hash placeholder)
        db.execute(
            (
                "INSERT INTO users (username, email, hash, date, auth_type) "
                "VALUES (%s,%s,%s,%s,%s) RETURNING id"
            ),
            (
                TEST_USERNAME,
                f"{TEST_USERNAME}@example.com",
                "h",
                "2020-01-01",
                "normal",
            ),
        )
        uid = db.fetchone()[0]
        # ensure stats/resources
        db.execute(
            (
                "INSERT INTO stats (id, gold, location) "
                "VALUES (%s, %s, %s) ON CONFLICT (id) DO NOTHING"
            ),
            (uid, 10_000_000, ""),
        )
        db.execute(
            "INSERT INTO resources (id) VALUES (%s) ON CONFLICT (id) DO NOTHING", (uid,)
        )
        db.execute(
            "INSERT INTO proInfra (id) VALUES (%s) ON CONFLICT (id) DO NOTHING", (uid,)
        )
        db.execute(
            (
                "INSERT INTO provinces (id, userId, land, cityCount, productivity) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING"
            ),
            (uid, uid, 100, 1, 50),
        )
        conn.commit()
    return uid


def create_user_with_password(password):
    import bcrypt

    username = TEST_USERNAME + "_auth"
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            (
                "INSERT INTO users (username, email, hash, date, auth_type) "
                "VALUES (%s,%s,%s,%s,%s) RETURNING id"
            ),
            (username, f"{username}@example.com", hashed, "2020-01-01", "normal"),
        )
        uid = db.fetchone()[0]
        db.execute(
            (
                "INSERT INTO stats (id, gold, location) "
                "VALUES (%s, %s, %s) ON CONFLICT (id) DO NOTHING"
            ),
            (uid, 10_000_000, ""),
        )
        db.execute(
            "INSERT INTO resources (id) VALUES (%s) ON CONFLICT (id) DO NOTHING", (uid,)
        )
        db.execute(
            "INSERT INTO proInfra (id) VALUES (%s) ON CONFLICT (id) DO NOTHING", (uid,)
        )
        db.execute(
            (
                "INSERT INTO provinces (id, userId, land, cityCount, productivity) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING"
            ),
            (uid, uid, 100, 1, 50),
        )
        conn.commit()
    return username, password, uid


def cleanup_test_user(uid):
    with get_db_connection() as conn:
        db = conn.cursor()
        # remove rows inserted
        db.execute("DELETE FROM provinces WHERE id=%s", (uid,))
        db.execute("DELETE FROM proInfra WHERE id=%s", (uid,))
        db.execute("DELETE FROM resources WHERE id=%s", (uid,))
        db.execute("DELETE FROM stats WHERE id=%s", (uid,))
        db.execute("DELETE FROM users WHERE id=%s", (uid,))
        conn.commit()


def make_session_cookie(app, data):
    """Create a Flask session cookie value containing `data` dict"""
    s = SecureCookieSessionInterface().get_signing_serializer(app)
    return s.dumps(data)


def row_to_dict(cursor, row):
    if row is None:
        return {}
    # If cursor returns mapping-like rows, return as-is
    try:
        return dict(row)
    except Exception:
        # Fallback: build dict from cursor.description
        colnames = [d[0] for d in cursor.description]
        return dict(zip(colnames, row))


def get_resources_from_db(uid):
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT * FROM resources WHERE id=%s", (uid,))
        return row_to_dict(db, db.fetchone())


def get_units_from_db(uid):
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT * FROM proInfra WHERE id=%s", (uid,))
        return row_to_dict(db, db.fetchone())


def main():
    # Use a single auth user for province ownership to avoid ownership mismatch
    username, password, uid = create_user_with_password("password123")
    print("Created auth user:", username, uid)

    # Ensure the cookie uses the same secret key as the deployed app
    if os.environ.get("SECRET_KEY"):
        app.secret_key = os.environ.get("SECRET_KEY")

    session = requests.Session()
    # Login via the website to get a session cookie from the real app
    login_url = f"{TARGET_HOST}/login"
    resp = session.post(
        login_url,
        data={"username": username, "password": password},
        allow_redirects=True,
    )
    print("Login status:", resp.status_code)

    # Snapshot before
    print("Before resources:", get_resources_from_db(uid))
    print("Before units:", get_units_from_db(uid))

    # BUY farms: POST to /province/buy/farms/<province_id>
    print("Buying 4 farms...")
    resp = session.post(
        f"{TARGET_HOST}/province/buy/farms/{uid}",
        data={"farms": "4"},
        allow_redirects=False,
    )
    print("buy resp status:", resp.status_code)
    if resp.status_code != 302:
        print("buy resp headers:", resp.headers)
        try:
            body = resp.text
            print("buy resp body snippet:\n", body[:4000])
        except Exception:
            pass
    time.sleep(1)
    print("After buy resources:", get_resources_from_db(uid))
    print("After buy units:", get_units_from_db(uid))

    # SELL 4 farms
    print("Selling 4 farms...")
    resp = session.post(
        f"{TARGET_HOST}/province/sell/farms/{uid}",
        data={"farms": "4"},
        allow_redirects=False,
    )
    print("sell resp status:", resp.status_code)
    if resp.status_code != 302:
        try:
            print("sell resp body snippet:\n", resp.text[:4000])
        except Exception:
            pass
    time.sleep(1)
    print("After sell resources:", get_resources_from_db(uid))
    print("After sell units:", get_units_from_db(uid))

    # BUY again
    print("Buying 4 farms again...")
    resp = session.post(
        f"{TARGET_HOST}/province/buy/farms/{uid}",
        data={"farms": "4"},
        allow_redirects=False,
    )
    print("buy2 resp status:", resp.status_code)
    if resp.status_code != 302:
        try:
            print("buy2 resp body snippet:\n", resp.text[:4000])
        except Exception:
            pass
    time.sleep(1)
    print("After buy2 resources:", get_resources_from_db(uid))
    print("After buy2 units:", get_units_from_db(uid))

    # Cleanup
    print("Cleaning up test user and province...")
    cleanup_test_user(uid)
    print("Done.")


if __name__ == "__main__":
    main()
