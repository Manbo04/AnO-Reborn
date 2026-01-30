from database import get_db_connection
from attack_scripts.Nations import Economy as AttackEconomy


def test_get_particular_resources_returns_existing_values():
    # Create a temporary user with a known steel value
    import time

    username = f"test_eco_user_{int(time.time() * 1000)}"
    email = f"{username}@example.com"
    with get_db_connection() as conn:
        db = conn.cursor()
        # create a unique temporary user
        db.execute(
            (
                "INSERT INTO users (username, email, hash, date, auth_type) VALUES "
                "(%s,%s,%s,%s,%s) RETURNING id"
            ),
            (username, email, "x", "2020-01-01", "normal"),
        )
        uid = db.fetchone()[0]
        db.execute(
            "INSERT INTO stats (id, gold, location) VALUES (%s,%s,%s)",
            (uid, 20000000, "Test"),
        )
        db.execute("INSERT INTO resources (id, steel) VALUES (%s,%s)", (uid, 123))
        db.execute("INSERT INTO military (id) VALUES (%s)", (uid,))
        conn.commit()

    try:
        e = AttackEconomy(uid)
        rd = e.get_particular_resources(["steel"])
        assert isinstance(rd, dict)
        assert rd.get("steel") == 123
    finally:
        # cleanup
        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute("DELETE FROM wars WHERE attacker=%s OR defender=%s", (uid, uid))
            db.execute("DELETE FROM resources WHERE id=%s", (uid,))
            db.execute("DELETE FROM stats WHERE id=%s", (uid,))
            db.execute("DELETE FROM users WHERE id=%s", (uid,))
            db.execute("DELETE FROM military WHERE id=%s", (uid,))
            conn.commit()
