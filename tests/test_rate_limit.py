import psycopg2
import os
import requests
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
    db.execute("SELECT key FROM keys WHERE key=%s", (key_value,))
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

    # Ensure no leftover signup attempts exist for this IP (tests may be run in order)
    conn = psycopg2.connect(
        database=os.getenv("PG_DATABASE"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        host=os.getenv("PG_HOST"),
        port=os.getenv("PG_PORT"),
    )
    db = conn.cursor()
    db.execute("DELETE FROM signup_attempts WHERE ip_address=%s", (test_ip,))
    conn.commit()
    db.close()
    conn.close()

    # Ensure recaptcha is bypassed in test env (some CI/dev envs set secret)
    import signup as signup_module

    signup_module.verify_recaptcha = lambda resp: True

    headers = {"X-Forwarded-For": test_ip}

    # Rather than attempt full signup flow (which can depend on external
    # config like recaptcha), assert rate-limiter behavior by seeding
    # three attempts and checking the next POST is rejected.
    conn = psycopg2.connect(
        database=os.getenv("PG_DATABASE"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        host=os.getenv("PG_HOST"),
        port=os.getenv("PG_PORT"),
    )
    db = conn.cursor()
    sql = (
        "INSERT INTO signup_attempts (ip_address, ip, attempt_time, successful) "
        "VALUES (%s, %s, NOW(), FALSE)"
    )
    for _ in range(3):
        db.execute(sql, (test_ip, test_ip))
    conn.commit()
    db.close()
    conn.close()

    # Now the next signup POST should be rate limited (429)
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
