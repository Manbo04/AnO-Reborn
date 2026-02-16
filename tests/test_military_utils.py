from database import get_db_cursor
from attack_scripts.Nations import Military


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


def test_get_military_and_get_limits_return_types():
    with get_db_cursor() as db:
        uid = _create_dummy_user(db)
        db.execute(
            "INSERT INTO resources (id) VALUES (%s) ON CONFLICT DO NOTHING", (uid,)
        )
        db.execute(
            (
                "INSERT INTO stats (id, gold, location) "
                "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING"
            ),
            (uid, 1000, "T"),
        )
        db.execute(
            (
                "INSERT INTO military (id, soldiers, tanks, artillery, bombers, "
                "fighters, apaches, submarines, destroyers, cruisers) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT DO NOTHING"
            ),
            (uid, 10, 2, 3, 4, 5, 6, 0, 0, 0),
        )

        db.connection.commit()

        mil = Military.get_military(uid)
        assert isinstance(mil, dict)
        for k in ("soldiers", "fighters", "apaches"):
            assert k in mil
            assert isinstance(mil[k], int)

        limits = Military.get_limits(uid)
        assert isinstance(limits, dict)
        expected_limit_keys = {
            "soldiers",
            "tanks",
            "artillery",
            "bombers",
            "fighters",
            "apaches",
            "destroyers",
            "cruisers",
            "submarines",
            "spies",
            "icbms",
            "nukes",
        }
        assert expected_limit_keys.issubset(set(limits.keys()))

        # cleanup
        db.execute("DELETE FROM military WHERE id=%s", (uid,))
        db.execute("DELETE FROM resources WHERE id=%s", (uid,))
        db.execute("DELETE FROM stats WHERE id=%s", (uid,))
        db.execute("DELETE FROM users WHERE id=%s", (uid,))
        db.connection.commit()
