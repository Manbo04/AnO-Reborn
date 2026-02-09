import requests
import psycopg2
import os
import random
import string
from dotenv import load_dotenv
from init import BASE_URL

load_dotenv()

# Helper to register a new user via direct HTTP (uses the existing test key in DB)


def random_str(n=8):
    return "test_" + "".join(random.choice(string.ascii_lowercase) for _ in range(n))


def create_user(session, username=None, email=None, password="testpassword12345"):
    username = username or random_str()
    email = email or f"{username}@example.test"
    data = {
        "username": username,
        "email": email,
        "password": password,
        "confirmation": password,
        "key": os.environ.get("TEST_KEY", "testkey12345"),
        "continent": "1",
    }
    r = session.post(f"{BASE_URL}/signup", data=data, allow_redirects=True)
    return r.status_code in (200, 302), username, email


def cleanup_user(username, email):
    conn = psycopg2.connect(
        database=os.getenv("PG_DATABASE"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        host=os.getenv("PG_HOST"),
        port=os.getenv("PG_PORT"),
    )
    db = conn.cursor()
    try:
        db.execute(
            "SELECT id FROM users WHERE username=%s AND email=%s "
            "AND auth_type='normal'",
            (username, email),
        )
        r = db.fetchone()
        if r:
            uid = r[0]
            # remove related rows
            db.execute("DELETE FROM colBanksRequests WHERE reqId=%s", (uid,))
            db.execute("DELETE FROM coalitions WHERE userId=%s", (uid,))
            db.execute("DELETE FROM stats WHERE id=%s", (uid,))
            db.execute("DELETE FROM resources WHERE id=%s", (uid,))
            db.execute("DELETE FROM users WHERE id=%s", (uid,))
            conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


def test_coalition_bank_request_flow():
    s_leader = requests.Session()
    s_member = requests.Session()

    # Create leader user and register
    ok, leader_username, leader_email = create_user(s_leader)
    assert ok, "leader signup failed"

    # Leader creates a coalition
    coalition_name = "coal_" + random_str(6)
    data = {
        "type": "Open",
        "name": coalition_name,
        "description": "test coalition",
    }
    r = s_leader.post(
        f"{BASE_URL}/establish_coalition", data=data, allow_redirects=True
    )
    assert r.status_code in (200, 302)

    # Get coalition id from DB
    conn = psycopg2.connect(
        database=os.getenv("PG_DATABASE"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        host=os.getenv("PG_HOST"),
        port=os.getenv("PG_PORT"),
    )
    db = conn.cursor()
    db.execute("SELECT id FROM colNames WHERE name=%s", (coalition_name,))
    row = db.fetchone()
    assert row, "coalition not found in DB"
    colId = row[0]

    # Create a member user and have them request money from the bank
    ok, member_username, member_email = create_user(s_member)
    assert ok, "member signup failed"

    # Member posts a bank request (money)
    request_data = {"money": "10"}
    r = s_member.post(
        f"{BASE_URL}/request_from_bank/{colId}",
        data=request_data,
        allow_redirects=True,
    )
    assert r.status_code in (200, 302)

    # Verify DB: there should be a request in colBanksRequests
    db.execute(
        "SELECT id, reqId, amount, resource FROM colBanksRequests "
        "WHERE reqId IN (SELECT id FROM users WHERE username=%s)",
        (member_username,),
    )
    req_row = db.fetchone()
    assert req_row, "bank request not recorded in DB"

    # Leader accepts the bank request
    bank_id = req_row[0]
    r = s_leader.post(f"{BASE_URL}/accept_bank_request/{bank_id}", allow_redirects=True)
    assert r.status_code in (200, 302)

    # Verify the request is removed
    db.execute("SELECT id FROM colBanksRequests WHERE id=%s", (bank_id,))
    assert db.fetchone() is None

    # Cleanup
    db.execute("DELETE FROM colNames WHERE id=%s", (colId,))
    conn.commit()
    conn.close()

    cleanup_user(leader_username, leader_email)
    cleanup_user(member_username, member_email)
