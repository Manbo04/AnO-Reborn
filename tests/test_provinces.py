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

    # Register via the public endpoint and log in
    reg_data = {
        "username": username,
        "email": email,
        "password": password,
        "confirmation": password,
        "key": username,
        "continent": "europe",
    }
    _ = register_session.post(f"{BASE_URL}/signup", data=reg_data, allow_redirects=True)
    assert login(login_session), "Login failed in test setup"

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
