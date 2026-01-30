import importlib
from database import get_db_connection


def test_get_particular_resources_survives_reload():
    # Creates a temporary user, reloads the module (like tests that may do), and
    # asserts the canonical, cached implementation returns the expected value.
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            (
                "INSERT INTO users (username, email, hash, date, auth_type) VALUES "
                "(%s,%s,%s,%s,%s) RETURNING id"
            ),
            ("reload_user", "reload@example.invalid", "x", "2020-01-01", "normal"),
        )
        uid = db.fetchone()[0]
        db.execute(
            "INSERT INTO stats (id, gold, location) VALUES (%s,%s,%s)",
            (uid, 20000000, "Test"),
        )
        db.execute("INSERT INTO resources (id, steel) VALUES (%s,%s)", (uid, 321))
        db.execute("INSERT INTO military (id) VALUES (%s)", (uid,))
        conn.commit()

    try:
        # Reload the module like the test harness may do and construct an Economy
        m = importlib.reload(importlib.import_module("attack_scripts.Nations"))
        AttackEconomy = m.Economy
        e = AttackEconomy(uid)
        rd = e.get_particular_resources(["steel"])
        assert isinstance(rd, dict)
        assert rd.get("steel") == 321
    finally:
        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute("DELETE FROM resources WHERE id=%s", (uid,))
            db.execute("DELETE FROM stats WHERE id=%s", (uid,))
            db.execute("DELETE FROM users WHERE id=%s", (uid,))
            db.execute("DELETE FROM military WHERE id=%s", (uid,))
            conn.commit()
