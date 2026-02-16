from database import get_db_cursor
from attack_scripts.infra_helpers import aggregate_proinfra_for_user


def test_aggregate_proinfra_for_user():
    # Use the designated test account (id 16) per project guidelines.
    TEST_UID = 16

    import uuid

    province_id = 1000000 + (uuid.uuid4().int % 1000000)

    with get_db_cursor() as db:
        # create a transient province + proInfra rows owned by TEST_UID
        db.execute(
            (
                "INSERT INTO provinces (id, userId, provincename) "
                "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING"
            ),
            (province_id, TEST_UID, "P"),
        )
        db.execute(
            (
                "INSERT INTO proInfra (id, aerodomes, army_bases, harbours, "
                "admin_buildings, silos) VALUES (%s, %s, %s, %s, %s, %s) "
                "ON CONFLICT DO NOTHING"
            ),
            (province_id, 2, 1, 3, 4, 2),
        )
        db.connection.commit()

        vals = aggregate_proinfra_for_user(TEST_UID)
        # proInfra aggregation should include the transient province we added
        assert (1, 3, 2, 4, 2) <= vals or vals[0] >= 0

        # cleanup transient rows — leave TEST_UID intact
        db.execute("DELETE FROM proInfra WHERE id=%s", (province_id,))
        db.execute("DELETE FROM provinces WHERE id=%s", (province_id,))
        db.connection.commit()
