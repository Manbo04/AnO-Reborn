import os

# requests not used directly in this test module; tests use session fixtures instead
import psycopg2
from dotenv import load_dotenv
from init import BASE_URL
from test_auth import login_session

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

    url = f"{BASE_URL}/createprovince"
    data = {"name": "test_province"}
    login_session.post(url, data=data, allow_redirects=True)

    try:
        db.execute("SELECT id FROM provinces WHERE provincename=%s", (data["name"],))
        row = db.fetchone()
        if row is None:
            return False
    except Exception:
        return False
    return True


def test_create_province():
    assert create_province() is True
