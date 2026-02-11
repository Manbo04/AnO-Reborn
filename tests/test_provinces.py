from test_auth import login_session, login, register, register_session
import psycopg2
import os
import time
from dotenv import load_dotenv
from init import BASE_URL

load_dotenv()

load_dotenv()


def create_province():
    conn = psycopg2.connect(
        database=os.getenv("PG_DATABASE"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        host=os.getenv("PG_HOST"),
        port=os.getenv("PG_PORT"),
    )

    db = conn.cursor()

    # Ensure session is logged in
    if not login(login_session):
        register(register_session)
        assert login(login_session), "Login failed in test setup"

    # Create an independent test user and log in (avoids test ordering issues)
    username = f"provtest_{int(time.time())}"
    email = f"{username}@example.com"
    password = "testpass"
    # Ensure we have a registration key available
    try:
        db.execute("INSERT INTO keys (key) VALUES (%s)", (username,))
        conn.commit()
    except Exception:
        pass

    # Register via the public endpoint and wait for the DB to reflect the new user
    reg_data = {
        "username": username,
        "email": email,
        "password": password,
        "confirmation": password,
        "key": username,
        "continent": "europe",
    }
    signup_resp = register_session.post(
        f"{BASE_URL}/signup", data=reg_data, allow_redirects=True
    )

    # If signup fails (e.g., validation on CI), capture a short snippet of the
    # response body to make failures actionable in CI logs.
    if signup_resp.status_code != 200:
        try:
            snippet = signup_resp.text[:1000]
        except Exception:
            snippet = "<unavailable>"
        print(
            "DEBUG: signup failed",
            f"status={signup_resp.status_code}",
            f"len={len(signup_resp.text)}",
        )
        print("DEBUG: signup snippet:")
        print(snippet)

    # Wait up to ~10s for the signup to appear in the DB (mitigates race in CI)
    uid = None
    for _ in range(50):
        db.execute("SELECT id FROM users WHERE username=%s", (username,))
        row = db.fetchone()
        if row:
            uid = row[0]
            break
        time.sleep(0.2)

    assert uid is not None, (
        "Signup did not complete in time. "
        f"signup_status={signup_resp.status_code} "
        f"login_resp_len={len(signup_resp.text)}"
    )

    # Log the newly registered user into the session used for subsequent requests
    login_data = {"username": username, "password": password, "rememberme": "on"}
    resp = login_session.post(
        f"{BASE_URL}/login/", data=login_data, allow_redirects=False
    )
    # If login issued a redirect, follow it once
    if resp.status_code in (302, 303):
        login_session.get(f"{BASE_URL}/")

    # Give the session a short moment to propagate cookies
    for _ in range(10):
        if login_session.cookies.get_dict():
            break
        time.sleep(0.1)
    assert login_session.cookies.get_dict() != {}, "Login failed for registered user"

    # Give the new user enough gold to purchase a province
    try:
        db.execute("SELECT id FROM users WHERE username=%s", (username,))
        uid = db.fetchone()[0]
        db.execute(
            "INSERT INTO stats (id, gold, location) VALUES (%s,%s,%s) "
            "ON CONFLICT (id) DO UPDATE SET gold=%s, location=%s",
            (uid, 1000000, "", 1000000, ""),
        )
        conn.commit()
    except Exception:
        pass

    url = f"{BASE_URL}/createprovince"
    data = {"name": "test_province"}
    _ = login_session.post(url, data=data, allow_redirects=True)

    try:
        db.execute("SELECT id FROM provinces WHERE provincename=%s", (data["name"],))
        _ = db.fetchone()[0]
    except Exception:
        return False
    return True


def test_create_province():
    assert create_province() is True
