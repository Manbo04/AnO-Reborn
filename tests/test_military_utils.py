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
    # Use the designated test account (id 16) and restore its state after the test
    TEST_UID = 16

    with get_db_cursor() as db:
        # snapshot current military/resources/stats rows for TEST_UID
        db.execute("SELECT * FROM military WHERE id=%s", (TEST_UID,))
        orig_military = db.fetchone()

        db.execute("SELECT * FROM resources WHERE id=%s", (TEST_UID,))
        orig_resources = db.fetchone()

        db.execute("SELECT gold, location FROM stats WHERE id=%s", (TEST_UID,))
        orig_stats = db.fetchone()

        # ensure rows exist and set deterministic test values (restore later)
        db.execute(
            "INSERT INTO resources (id) VALUES (%s) ON CONFLICT DO NOTHING", (TEST_UID,)
        )
        db.execute(
            (
                "INSERT INTO stats (id, gold, location) VALUES (%s, %s, %s) "
                "ON CONFLICT (id) DO UPDATE SET gold=%s, location=%s"
            ),
            (TEST_UID, 1000, "T", 1000, "T"),
        )
        db.execute(
            (
                "INSERT INTO military (id, soldiers, tanks, artillery, bombers, "
                "fighters, apaches, submarines, destroyers, cruisers) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (id) DO UPDATE SET "
                "soldiers=%s, tanks=%s, artillery=%s, bombers=%s, fighters=%s, "
                "apaches=%s, submarines=%s, destroyers=%s, cruisers=%s"
            ),
            (TEST_UID, 10, 2, 3, 4, 5, 6, 0, 0, 0, 10, 2, 3, 4, 5, 6, 0, 0, 0),
        )
        db.connection.commit()

        mil = Military.get_military(TEST_UID)
        assert isinstance(mil, dict)
        for k in ("soldiers", "fighters", "apaches"):
            assert k in mil
            assert isinstance(mil[k], int)

        limits = Military.get_limits(TEST_UID)
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

        # restore original rows
        if orig_military:
            # best-effort restore using UPDATE
            db.execute(
                (
                    "UPDATE military SET soldiers=%s, artillery=%s, tanks=%s, "
                    "bombers=%s, fighters=%s, apaches=%s, submarines=%s, "
                    "destroyers=%s, cruisers=%s WHERE id=%s"
                ),
                (
                    orig_military[1],
                    orig_military[2],
                    orig_military[0],
                    orig_military[3],
                    orig_military[4],
                    orig_military[5],
                    orig_military[8],
                    orig_military[6],
                    orig_military[7],
                    TEST_UID,
                ),
            )
        else:
            db.execute("DELETE FROM military WHERE id=%s", (TEST_UID,))

        if orig_resources:
            # no reliable column mapping here — leave as-is.
            # (we intentionally avoid destructive changes to the shared test account)
            pass
        else:
            db.execute("DELETE FROM resources WHERE id=%s", (TEST_UID,))

        if orig_stats:
            db.execute(
                "UPDATE stats SET gold=%s, location=%s WHERE id=%s",
                (orig_stats[0], orig_stats[1], TEST_UID),
            )
        else:
            db.execute("DELETE FROM stats WHERE id=%s", (TEST_UID,))

        db.connection.commit()
