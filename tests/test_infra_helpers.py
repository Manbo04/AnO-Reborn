from database import get_db_cursor
from attack_scripts.infra_helpers import aggregate_proinfra_for_user


def _create_dummy_user(db):
    import uuid

    username = f"testuser_{uuid.uuid4().hex[:8]}"
    db.execute(
        (
            "INSERT INTO users (username, email, hash, date, auth_type) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id"
        ),
        (username, f"{username}@example.invalid", "x", "1970-01-01", "normal"),
    )
    return db.fetchone()[0]


def test_aggregate_proinfra_for_user():
    with get_db_cursor() as db:
        uid = _create_dummy_user(db)

        # create province + proInfra rows
        db.execute(
            (
                "INSERT INTO provinces (id, userId, provincename) "
                "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING"
            ),
            (uid, uid, "P"),
        )
        db.execute(
            (
                "INSERT INTO proInfra (id, aerodomes, army_bases, harbours, "
                "admin_buildings, silos) VALUES (%s, %s, %s, %s, %s, %s) "
                "ON CONFLICT DO NOTHING"
            ),
            (uid, 2, 1, 3, 4, 2),
        )
        db.connection.commit()

        vals = aggregate_proinfra_for_user(uid)
        assert vals == (1, 3, 2, 4, 2)

        # cleanup
        db.execute("DELETE FROM proInfra WHERE id=%s", (uid,))
        db.execute("DELETE FROM provinces WHERE id=%s", (uid,))
        db.execute("DELETE FROM users WHERE id=%s", (uid,))
        db.connection.commit()
