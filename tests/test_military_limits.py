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
    """Verify apaches are limited by army_bases while fighters/bombers use aerodomes.

    Use the designated test account (id 16) and a transient province id so the
    test leaves no trace and follows project testing guidelines.
    """
    TEST_UID = 16

    import uuid

    transient_province = 2000000 + (uuid.uuid4().int % 1000000)

    with get_db_cursor() as db:
        # snapshot existing military row for TEST_UID (restore later)
        db.execute("SELECT * FROM military WHERE id=%s", (TEST_UID,))
        orig_military = db.fetchone()

        # ensure resources/stats exist for TEST_UID but don't overwrite originals
        db.execute(
            "INSERT INTO resources (id) VALUES (%s) ON CONFLICT DO NOTHING", (TEST_UID,)
        )
        db.execute(
            (
                "INSERT INTO stats (id, gold, location) "
                "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING"
            ),
            (TEST_UID, 1000000, "T"),
        )

        # ensure military row exists and set manpower/defaults for test
        db.execute(
            "INSERT INTO military (id) VALUES (%s) ON CONFLICT DO NOTHING", (TEST_UID,)
        )
        db.execute("UPDATE military SET manpower=%s WHERE id=%s", (1000, TEST_UID))

        # snapshot specific unit counts, then set them to known values for the test
        db.execute(
            ("SELECT fighters, bombers, apaches FROM military " "WHERE id=%s"),
            (TEST_UID,),
        )
        db.fetchone()  # snapshot not needed here; we'll restore using orig_military
        db.execute(
            ("UPDATE military SET fighters=%s, bombers=%s, apaches=%s " "WHERE id=%s"),
            (0, 0, 0, TEST_UID),
        )

        # create a transient province + proInfra owned by TEST_UID
        db.execute(
            (
                "INSERT INTO provinces (id, userId, provincename) "
                "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING"
            ),
            (transient_province, TEST_UID, "TestProvince"),
        )
        db.execute(
            (
                "INSERT INTO proInfra (id, aerodomes, army_bases) "
                "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING"
            ),
            (transient_province, 1, 1),
        )
        db.connection.commit()

        # With transient proInfra added, capacity should match aggregated infra
        from attack_scripts.infra_helpers import aggregate_proinfra_for_user

        infra = aggregate_proinfra_for_user(TEST_UID)
        aerodomes_total = infra[2]
        army_bases_total = infra[0]

        limits = Military.get_limits(TEST_UID)
        assert limits["fighters"] == max(0, aerodomes_total * 5 - 0)
        assert limits["bombers"] == max(0, aerodomes_total * 5 - 0)

        # Apaches limited by army_bases (we set apaches to 0 earlier)
        assert limits["apaches"] == max(0, army_bases_total * 5 - 0)

        # Simulate buying 5 apaches by updating military for TEST_UID
        db.execute("UPDATE military SET apaches=%s WHERE id=%s", (5, TEST_UID))
        db.connection.commit()
        limits_after = Military.get_limits(TEST_UID)
        # after buying 5 apaches, apache remaining capacity should reflect army_bases
        assert limits_after["apaches"] == max(0, army_bases_total * 5 - 5)
        # fighters/bombers unaffected by apaches count
        assert limits_after["fighters"] == max(0, aerodomes_total * 5 - 0)
        assert limits_after["bombers"] == max(0, aerodomes_total * 5 - 0)

        # cleanup transient rows and restore original military row
        db.execute("DELETE FROM proInfra WHERE id=%s", (transient_province,))
        db.execute("DELETE FROM provinces WHERE id=%s", (transient_province,))

        if orig_military:
            # best-effort restore: write back original values where possible
            try:
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
            except Exception:
                # if restore fails, at least reset apaches to 0
                # to avoid leaving state changed
                db.execute("UPDATE military SET apaches=0 WHERE id=%s", (TEST_UID,))
        else:
            db.execute("DELETE FROM military WHERE id=%s", (TEST_UID,))

        db.connection.commit()
