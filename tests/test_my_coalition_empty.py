"""Coalition empty-state: no 500 when player has no coalition."""
import uuid

import pytest

pytestmark = pytest.mark.no_server


@pytest.fixture
def client():
    from app import app

    with app.test_client() as c:
        yield c


def test_my_coalition_without_membership_shows_friendly_page(client):
    from database import get_db_cursor

    with get_db_cursor() as db:
        username = f"no_col_{uuid.uuid4().hex[:8]}"
        db.execute(
            (
                "INSERT INTO users (username, email, hash, date, auth_type) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id"
            ),
            (username, f"{username}@example.invalid", "x", "1970-01-01", "normal"),
        )
        user_id = db.fetchone()[0]
        db.execute("DELETE FROM coalitions_legacy WHERE userid=%s", (user_id,))

    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    resp = client.get("/my_coalition", follow_redirects=True)
    assert resp.status_code == 200
    assert b"No coalition yet" in resp.data
    assert b"Browse coalitions" in resp.data
    assert b"Error</h1>" not in resp.data
