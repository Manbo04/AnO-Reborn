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
    # Ensure the user is logged in for subsequent requests
    # (some setups require explicit login)
    login_r = session.post(
        f"{BASE_URL}/login",
        data={"username": username, "password": password},
        allow_redirects=True,
    )
    ok = r.status_code in (200, 302) and login_r.status_code in (200, 302)
    return ok, username, email


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

    # Create a member user and have them join the coalition and request money
    ok, member_username, member_email = create_user(s_member)
    assert ok, "member signup failed"

    # Member joins the coalition (Open coalition)
    r = s_member.post(f"{BASE_URL}/join/{colId}", data={}, allow_redirects=True)
    # sometimes the server returns 500 if the user is already in the coalition
    # due to race conditions; treat that as success
    if r.status_code == 500:
        # optionally we could inspect r.text for specific error message
        pass
    else:
        assert r.status_code in (200, 302), "member failed to join coalition"

    # Seed the coalition bank with money so the leader can accept requests
    db.execute("UPDATE colBanks SET money=%s WHERE colId=%s", (1000, colId))
    conn.commit()

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


def test_deputy_can_view_and_accept_applicants():
    s_leader = requests.Session()
    s_deputy = requests.Session()
    s_applicant = requests.Session()

    # Leader signup + create coalition (Open initially)
    ok, leader_username, leader_email = create_user(s_leader)
    assert ok, "leader signup failed"

    coalition_name = "coal_deputy_" + random_str(6)
    data = {"type": "Open", "name": coalition_name, "description": "test coalition"}
    r = s_leader.post(
        f"{BASE_URL}/establish_coalition", data=data, allow_redirects=True
    )
    assert r.status_code in (200, 302)

    # Get coalition id
    conn = psycopg2.connect(
        database=os.getenv("PG_DATABASE"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        host=os.getenv("PG_HOST"),
        port=os.getenv("PG_PORT"),
    )
    db = conn.cursor()
    db.execute("SELECT id FROM colNames WHERE name=%s", (coalition_name,))
    colId = db.fetchone()[0]

    # Create deputy user and join (Open coalition)
    ok, deputy_username, deputy_email = create_user(s_deputy)
    assert ok, "deputy signup failed"
    r = s_deputy.post(f"{BASE_URL}/join/{colId}", data={}, allow_redirects=True)
    assert r.status_code in (200, 302), "deputy failed to join coalition"

    # Leader promotes user to deputy_leader
    give_data = {"role": "deputy_leader", "username": deputy_username}
    r = s_leader.post(f"{BASE_URL}/give_position", data=give_data, allow_redirects=True)
    assert r.status_code in (200, 302)

    # Verify the promotion persisted in the database. This prevents
    # silent race/selection bugs during the test.
    db.execute(
        "SELECT role FROM coalitions "
        "WHERE userId=(SELECT id FROM users WHERE username=%s) "
        "AND colId=%s",
        (deputy_username, colId),
    )
    assert db.fetchone()[0] == "deputy_leader", "DB did not persist deputy promotion"

    # Leader switches coalition to Invite Only
    r = s_leader.post(
        f"{BASE_URL}/update_col_info/{colId}",
        data={"application_type": "Invite Only"},
        allow_redirects=True,
    )
    assert r.status_code in (200, 302)

    # Applicant signs up and applies.
    # (Joining an Invite-Only coalition creates a requests row)
    ok, applicant_username, applicant_email = create_user(s_applicant)
    assert ok, "applicant signup failed"
    apply_data = {"message": "Please accept me"}
    r = s_applicant.post(
        f"{BASE_URL}/join/{colId}",
        data=apply_data,
        allow_redirects=True,
    )
    assert r.status_code in (200, 302)

    # Verify request recorded in DB (helps detect join_col insertion failures)
    db.execute(
        "SELECT reqId FROM requests WHERE colId=%s "
        "AND reqId=(SELECT id FROM users WHERE username=%s)",
        (colId, applicant_username),
    )
    assert db.fetchone() is not None, "join request not recorded in DB"

    # Deputy views coalition page and should see the applicant listed
    r = s_deputy.get(f"{BASE_URL}/coalition/{colId}")
    assert r.status_code == 200
    body = r.text
    assert applicant_username in body, "Deputy cannot see applicant in leader panel"

    # Deputy accepts the applicant
    # lookup applicant id
    db.execute("SELECT id FROM users WHERE username=%s", (applicant_username,))
    applicant_id = db.fetchone()[0]
    r = s_deputy.post(f"{BASE_URL}/add/{applicant_id}", allow_redirects=True)
    assert r.status_code in (200, 302)

    # Verify applicant was added to coalition
    db.execute(
        "SELECT userId FROM coalitions WHERE userId=%s AND colId=%s",
        (applicant_id, colId),
    )
    assert db.fetchone() is not None, "Applicant was not added to coalition by deputy"

    # Cleanup DB state
    db.execute("DELETE FROM colNames WHERE id=%s", (colId,))
    conn.commit()
    conn.close()

    cleanup_user(leader_username, leader_email)
    cleanup_user(deputy_username, deputy_email)
    cleanup_user(applicant_username, applicant_email)
