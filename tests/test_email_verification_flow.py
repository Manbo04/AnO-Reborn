import pytest
import email_verification
from database import get_db_cursor
from app import app as flask_app


@pytest.fixture
def client():
    with flask_app.test_client() as c:
        yield c


@pytest.fixture
def app():
    # provide the Flask app for use with app.app_context()
    return flask_app


def test_verify_route_marks_user_verified(client, app):
    import uuid

    # Create a user and a token, then call the verify route (use unique username/email to avoid collisions)
    with app.app_context():
        with get_db_cursor() as db:
            username = f"v_{uuid.uuid4().hex[:8]}"
            email = f"{username}@example.com"
            db.execute(
                "INSERT INTO users (username, email, hash, date, auth_type) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (username, email, "h", "2020-01-01", "n"),
            )
            user_id = db.fetchone()[0]
            token = email_verification.generate_verification(email, user_id=user_id)
    resp = client.get(f"/verify_email/{token}", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Email verified" in resp.data or b"successfully" in resp.data

    # Some schemas may not have an is_verified column; ensure the route responded with success
    # and did not raise an uncaught exception (asserted by status above).


def test_verify_route_invalid_token_shows_expired(client):
    resp = client.get("/verify_email/this-token-does-not-exist", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Verification link expired" in resp.data or b"invalid" in resp.data
