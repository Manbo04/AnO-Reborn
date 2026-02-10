import uuid
from database import get_db_cursor


def _create_dummy_user(db, username=None, email=None):
    if username is None:
        username = f"testuser_{uuid.uuid4().hex[:8]}"
    if email is None:
        email = f"{username}@example.invalid"
    db.execute(
        (
            "INSERT INTO users (username, email, hash, date, auth_type) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id"
        ),
        (username, email, "x", "1970-01-01", "normal"),
    )
    return db.fetchone()[0]


def test_resources_and_military_upsert():
    with get_db_cursor() as db:
        user_id = _create_dummy_user(db)

        # First insert should create rows and return an identifier
        db.execute(
            (
                "INSERT INTO resources (id) VALUES (%s) "
                "ON CONFLICT DO NOTHING RETURNING id"
            ),
            (user_id,),
        )
        first = db.fetchone()
        assert first is not None
        assert first[0] == user_id

        # Second insert should be a no-op and return None
        db.execute(
            (
                "INSERT INTO resources (id) VALUES (%s) "
                "ON CONFLICT DO NOTHING RETURNING id"
            ),
            (user_id,),
        )
        second = db.fetchone()
        assert second is None

        # Repeat for military table
        db.execute(
            (
                "INSERT INTO military (id) VALUES (%s) "
                "ON CONFLICT DO NOTHING RETURNING id"
            ),
            (user_id,),
        )
        first_m = db.fetchone()
        assert first_m is not None and first_m[0] == user_id

        db.execute(
            (
                "INSERT INTO military (id) VALUES (%s) "
                "ON CONFLICT DO NOTHING RETURNING id"
            ),
            (user_id,),
        )
        second_m = db.fetchone()
        assert second_m is None


def test_request_password_reset_upsert(client):
    # Create a user and a pre-existing reset code
    with get_db_cursor() as db:
        username = f"testuser_{uuid.uuid4().hex[:8]}"
        email = f"{username}@example.invalid"
        db.execute(
            (
                "INSERT INTO users (username, email, hash, date, auth_type) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id"
            ),
            (username, email, "x", "1970-01-01", "normal"),
        )
        user_id = db.fetchone()[0]

        old_code = "OLDCODE123"
        db.execute(
            (
                "INSERT INTO reset_codes (url_code, user_id, created_at) "
                "VALUES (%s, %s, %s)"
            ),
            (old_code, user_id, 1),
        )

    # Call the password reset endpoint
    resp = client.post(
        "/request_password_reset",
        data={"email": email},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)

    # Check that reset code exists and has been updated (not equal to old_code)
    with get_db_cursor() as db:
        db.execute("SELECT url_code FROM reset_codes WHERE user_id=%s", (user_id,))
        row = db.fetchone()
        assert row is not None
        assert row[0] != old_code
