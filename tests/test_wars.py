import pytest
import requests
import psycopg2
import os
from dotenv import load_dotenv
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from init import BASE_URL

load_dotenv()


@pytest.fixture(scope="module")
def login_session():
    return requests.Session()


@pytest.fixture(scope="module")
def users():
    users = [
        {
            "username": "waruser1",
            "email": "waruser1@example.com",
            "password": "testpass",
            "confirmation": "testpass",
            "key": "key1",
            "continent": "Europe",
        },
        {
            "username": "waruser2",
            "email": "waruser2@example.com",
            "password": "testpass",
            "confirmation": "testpass",
            "key": "key2",
            "continent": "Asia",
        },
    ]
    conn = psycopg2.connect(
        database=os.getenv("PG_DATABASE"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        host=os.getenv("PG_HOST"),
        port=os.getenv("PG_PORT"),
    )
    db = conn.cursor()
    import bcrypt
    import datetime

    # Clean up users and keys before test
    for user in users:
        db.execute(
            "DELETE FROM stats WHERE id IN (SELECT id FROM users WHERE username=%s)",
            (user["username"],),
        )
        db.execute(
            "DELETE FROM military WHERE id IN (SELECT id FROM users WHERE username=%s)",
            (user["username"],),
        )
        db.execute(
            "DELETE FROM resources WHERE id IN (SELECT id FROM users WHERE username=%s)",
            (user["username"],),
        )
        db.execute(
            "DELETE FROM upgrades WHERE user_id IN (SELECT id FROM users WHERE username=%s)",
            (user["username"],),
        )
        db.execute(
            "DELETE FROM policies WHERE user_id IN (SELECT id FROM users WHERE username=%s)",
            (user["username"],),
        )
        db.execute("DELETE FROM users WHERE username=%s", (user["username"],))
        db.execute("DELETE FROM keys WHERE key=%s", (user["key"],))
    conn.commit()
    # Create keys and users directly in DB
    for user in users:
        db.execute(
            "INSERT INTO keys (key) VALUES (%s) ON CONFLICT DO NOTHING", (user["key"],)
        )
        # Hash password as in signup.py
        hashed = bcrypt.hashpw(
            user["password"].encode("utf-8"), bcrypt.gensalt(14)
        ).decode("utf-8")
        db.execute(
            "INSERT INTO users (username, email, date, hash, auth_type) VALUES (%s, %s, %s, %s, %s)",
            (
                user["username"],
                user["email"],
                str(datetime.date.today()),
                hashed,
                "normal",
            ),
        )
        db.execute("SELECT id FROM users WHERE username = (%s)", (user["username"],))
        from database import fetchone_first

        user_id = fetchone_first(db, 0)
        db.execute(
            "INSERT INTO stats (id, location) VALUES (%s, %s)",
            (user_id, user["continent"]),
        )
        db.execute("INSERT INTO military (id) VALUES (%s)", (user_id,))
        db.execute("INSERT INTO resources (id) VALUES (%s)", (user_id,))
        db.execute("INSERT INTO upgrades (user_id) VALUES (%s)", (user_id,))
        db.execute("INSERT INTO policies (user_id) VALUES (%s)", (user_id,))
        conn.commit()
    return users


def test_declare_war(login_session, users):
    # Print user record and hash from DB for debugging
    conn = psycopg2.connect(
        database=os.getenv("PG_DATABASE"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        host=os.getenv("PG_HOST"),
        port=os.getenv("PG_PORT"),
    )
    db = conn.cursor()
    db.execute("SELECT * FROM users WHERE username=%s", (users[0]["username"],))
    user_row = db.fetchone()
    # Use assertions rather than printing for test hygiene
    assert user_row is not None
    hash_from_db = user_row[4] if len(user_row) > 4 else None
    assert hash_from_db is not None
    import bcrypt

    assert bcrypt.checkpw(
        users[0]["password"].encode("utf-8"), hash_from_db.encode("utf-8")
    )
    conn.close()
    login_resp = login_session.post(
        f"{BASE_URL}/login",
        data={"username": users[0]["username"], "password": users[0]["password"]},
    )
    assert login_resp.status_code in (200, 302)
    conn = psycopg2.connect(
        database=os.getenv("PG_DATABASE"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        host=os.getenv("PG_HOST"),
        port=os.getenv("PG_PORT"),
    )
    db = conn.cursor()
    db.execute("SELECT id FROM users WHERE username=%s", (users[1]["username"],))
    from database import fetchone_first

    defender_id = fetchone_first(db, 0)
    data = {"defender": defender_id, "warType": "Raze", "description": "Test war"}
    r = login_session.post(f"{BASE_URL}/declare_war", data=data, allow_redirects=True)
    assert r.status_code == 200 or r.status_code == 302
    db.execute(
        "SELECT * FROM wars WHERE attacker=(SELECT id FROM users WHERE username=%s) AND defender=%s AND peace_date IS NULL",
        (users[0]["username"], defender_id),
    )
    war = db.fetchone()
    assert war is not None


def test_wars_display(login_session, users):
    r = login_session.get(f"{BASE_URL}/wars")
    assert r.status_code == 200
    assert "Ongoing Wars" in r.text


def test_peace_offer(login_session, users):
    conn = psycopg2.connect(
        database=os.getenv("PG_DATABASE"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        host=os.getenv("PG_HOST"),
        port=os.getenv("PG_PORT"),
    )
    db = conn.cursor()
    db.execute("SELECT id FROM wars WHERE peace_date IS NULL ORDER BY id DESC LIMIT 1")
    from database import fetchone_first

    war_id = fetchone_first(db, 0)
    db.execute("SELECT defender FROM wars WHERE id=%s", (war_id,))
    enemy_id = fetchone_first(db, 0)
    data = {"money": "100"}
    r = login_session.post(
        f"{BASE_URL}/send_peace_offer/{war_id}/{enemy_id}",
        data=data,
        allow_redirects=True,
    )
    assert r.status_code == 200 or r.status_code == 302
    db.execute("SELECT peace_offer_id FROM wars WHERE id=%s", (war_id,))
    from database import fetchone_first

    offer_id = fetchone_first(db, 0)
    assert offer_id is not None


def test_war_result(login_session, users):
    r = login_session.get(f"{BASE_URL}/warResult")
    assert r.status_code == 200
    assert "winner" in r.text or "There is no winner" in r.text
