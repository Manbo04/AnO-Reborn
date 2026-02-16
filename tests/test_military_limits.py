import uuid
from database import get_db_cursor
from attack_scripts.Nations import Military


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


def test_apaches_do_not_consume_aerodome_capacity():
    """Verify apaches are limited by army_bases while fighters/bombers use aerodomes."""
    with get_db_cursor() as db:
        user_id = _create_dummy_user(db)

        # ensure supporting rows exist
        db.execute(
            "INSERT INTO resources (id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,)
        )
        db.execute(
            (
                "INSERT INTO stats (id, gold, location) "
                "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING"
            ),
            (user_id, 1000000, "T"),
        )
        # create a military row with defaults (safer than specifying partial columns)
        db.execute(
            "INSERT INTO military (id) VALUES (%s) ON CONFLICT DO NOTHING",
            (user_id,),
        )
        db.execute("UPDATE military SET manpower=%s WHERE id=%s", (1000, user_id))

        # create a province owned by the user and set infra
        db.execute(
            (
                "INSERT INTO provinces (id, userId, provincename) "
                "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING"
            ),
            (user_id, user_id, "TestProvince"),
        )
        db.execute(
            (
                "INSERT INTO proInfra (id, aerodomes, army_bases) "
                "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING"
            ),
            (user_id, 1, 1),
        )
        # commit so other connections can see the rows
        # (Military.get_limits opens a new cursor)
        db.connection.commit()

        # With 1 aerodome -> fighters/bombers capacity should be 5
        limits = Military.get_limits(user_id)
        assert limits["fighters"] == 5
        assert limits["bombers"] == 5

        # With 1 army_base -> apaches capacity should be 5 (separate)
        assert limits["apaches"] == 5

        # Simulate buying 5 apaches by updating military.
        # Fighters/bombers limit must remain 5
        db.execute("UPDATE military SET apaches=%s WHERE id=%s", (5, user_id))
        db.connection.commit()
        limits_after = Military.get_limits(user_id)
        assert limits_after["apaches"] == 0
        # fighters/bombers unaffected by apaches count
        assert limits_after["fighters"] == 5
        assert limits_after["bombers"] == 5

        # Clean up (best-effort)
        db.execute("DELETE FROM proInfra WHERE id=%s", (user_id,))
        db.execute("DELETE FROM provinces WHERE id=%s", (user_id,))
        db.execute("DELETE FROM military WHERE id=%s", (user_id,))
        db.execute("DELETE FROM resources WHERE id=%s", (user_id,))
        db.execute("DELETE FROM stats WHERE id=%s", (user_id,))
        db.execute("DELETE FROM users WHERE id=%s", (user_id,))
        db.connection.commit()
