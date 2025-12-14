import os

import credentials
import psycopg2
import requests
from dotenv import load_dotenv
from init import BASE_URL

load_dotenv()

login_session = requests.Session()
register_session = requests.Session()


def delete_user(username, email, session):
    conn = psycopg2.connect(
        database=os.getenv("PG_DATABASE"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        host=os.getenv("PG_HOST"),
        port=os.getenv("PG_PORT"),
    )

    db = conn.cursor()

    session.post(f"{BASE_URL}/delete_own_account")

    try:
        db.execute(
            (
                "SELECT id FROM users WHERE username=%s "
                "AND email=%s AND auth_type='normal'"
            ),
            (username, email),
        )
        row = db.fetchone()
        if row is None:
            return True
    except Exception:
        return True
    return False


def register(session):
    data = {
        "username": credentials.username,
        "email": credentials.email,
        "password": credentials.password,
        "confirmation": credentials.confirmation,
        "key": credentials.key,
        "continent": credentials.continent,
    }

    conn = psycopg2.connect(
        database=os.getenv("PG_DATABASE"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        host=os.getenv("PG_HOST"),
        port=os.getenv("PG_PORT"),
    )

    db = conn.cursor()
    # Clean up any existing user with this username/email to make test idempotent
    try:
        db.execute("SELECT id FROM users WHERE username=%s", (credentials.username,))
        existing = db.fetchone()
        if existing:
            uid = existing[0]
            db.execute("DELETE FROM stats WHERE id=%s", (uid,))
            db.execute("DELETE FROM military WHERE id=%s", (uid,))
            db.execute("DELETE FROM resources WHERE id=%s", (uid,))
            db.execute("DELETE FROM upgrades WHERE user_id=%s", (uid,))
            db.execute("DELETE FROM policies WHERE user_id=%s", (uid,))
            db.execute("DELETE FROM users WHERE id=%s", (uid,))

    except Exception:
        # If cleaning fails, continue — the test will report failures accordingly
        pass

    db.execute("INSERT INTO keys (key) VALUES (%s)", (credentials.key,))
    conn.commit()

    session.post(f"{BASE_URL}/signup", data=data, allow_redirects=True)

    if session.cookies.get_dict() == {}:
        return False

    try:
        db.execute(
            (
                "SELECT id FROM users WHERE username=%s "
                "AND email=%s AND auth_type='normal'"
            ),
            (credentials.username, credentials.email),
        )
        row = db.fetchone()
        if row is None:
            return False
    except Exception:
        return False

    return True


def login(session):
    data = {
        "username": credentials.username,
        "password": credentials.password,
        "rememberme": "on",
    }
    session.post(f"{BASE_URL}/login/", data=data, allow_redirects=False)
    return session.cookies.get_dict() != {}


def logout(session):
    base = session.cookies.get_dict()
    session.get(f"{BASE_URL}/logout")
    return session.cookies.get_dict() == {} and base != {}


def test_register():
    assert register(register_session) is True


def test_logout():
    assert logout(register_session) is True


def test_login():
    assert login(login_session) is True
