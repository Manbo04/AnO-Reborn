import requests
import psycopg2
import os
from dotenv import load_dotenv
from init import BASE_URL

load_dotenv()


def ensure_key_present(key_value):
    conn = psycopg2.connect(
        database=os.getenv("PG_DATABASE"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        host=os.getenv("PG_HOST"),
        port=os.getenv("PG_PORT"),
    )
    db = conn.cursor()
    db.execute("SELECT id FROM keys WHERE key=%s", (key_value,))
    if not db.fetchone():
        db.execute("INSERT INTO keys (key) VALUES (%s)", (key_value,))
        conn.commit()
    db.close()
    conn.close()


def test_ip_rate_limit():
    """Simulate multiple signups from same IP (via X-Forwarded-For)
    and expect 429 on the fourth.
    """
    session = requests.Session()
    test_ip = "1.2.3.4"

    # Ensure test registration key exists
    ensure_key_present("testkey12345")

    headers = {"X-Forwarded-For": test_ip}

    # Perform three signups (different usernames) - should be allowed
    for i in range(3):
        data = {
            "username": f"rl_user_{i}",
            "email": f"rl_user_{i}@example.com",
            "password": "testpassword123",
            "confirmation": "testpassword123",
            "key": "testkey12345",
            "continent": "1",
        }
        r = session.post(
            f"{BASE_URL}/signup", data=data, headers=headers, allow_redirects=False
        )
        # Redirect (302) or 200 is acceptable for successful signup flow
        assert r.status_code in (
            200,
            302,
        ), f"Unexpected status {r.status_code} for attempt {i}"

    # Fourth attempt should be rate-limited
    data = {
        "username": "rl_user_3",
        "email": "rl_user_3@example.com",
        "password": "testpassword123",
        "confirmation": "testpassword123",
        "key": "testkey12345",
        "continent": "1",
    }
    r = session.post(
        f"{BASE_URL}/signup", data=data, headers=headers, allow_redirects=False
    )
    assert r.status_code == 429 or ("Too many signup attempts" in r.text)
