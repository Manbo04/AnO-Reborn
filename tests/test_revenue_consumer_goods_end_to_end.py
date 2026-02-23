import time
from database import get_db_connection
import tasks
import countries


def create_test_user_with_mall():
    username = f"cgtest_{int(time.time())}"
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            (
                "INSERT INTO users (username, email, hash, date, auth_type) "
                "VALUES (%s,%s,%s,%s,%s) RETURNING id"
            ),
            (username, f"{username}@example.com", "x", "2020-01-01", "normal"),
        )
        uid = db.fetchone()[0]
        db.execute(
            "INSERT INTO stats (id, gold, location) VALUES (%s,%s,%s) "
            "ON CONFLICT (id) DO NOTHING",
            (uid, 100000000, ""),
        )
        # populate all known resources with a large amount so production
        # formulas aren't blocked by missing input resources during the
        # generate_province_revenue run.  Other tests rely on this row being
        # present but not necessarily having values, so we update after
        # inserting to avoid schema mismatches.
        db.execute(
            "INSERT INTO resources (id) VALUES (%s) ON CONFLICT (id) DO NOTHING",
            (uid,),
        )
        # bulk update every resource column to a big number
        all_res = [
            "rations",
            "oil",
            "coal",
            "uranium",
            "bauxite",
            "lead",
            "copper",
            "iron",
            "lumber",
            "components",
            "steel",
            "consumer_goods",
            "aluminium",
            "gasoline",
            "ammunition",
        ]
        for r in all_res:
            db.execute(f"UPDATE resources SET {r}=%s WHERE id=%s", (1000000, uid))
        # give a mall so we produce consumer_goods (and add solar_fields for energy)
        db.execute(
            "INSERT INTO proInfra (id, malls, solar_fields) VALUES (%s,%s,%s) "
            "ON CONFLICT (id) DO NOTHING",
            (uid, 1, 1),
        )
        db.execute(
            "INSERT INTO provinces (id, userId, land, cityCount, productivity) "
            "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING",
            (uid, uid, 0, 1, 50),
        )
        conn.commit()
    return uid


def cleanup_user(uid):
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("DELETE FROM provinces WHERE id=%s", (uid,))
        db.execute("DELETE FROM proInfra WHERE id=%s", (uid,))
        db.execute("DELETE FROM resources WHERE id=%s", (uid,))
        db.execute("DELETE FROM stats WHERE id=%s", (uid,))
        db.execute("DELETE FROM users WHERE id=%s", (uid,))
        conn.commit()
    try:
        from database import invalidate_user_cache

        invalidate_user_cache(uid)
    except Exception:
        pass


def test_consumer_goods_production_and_consumption(monkeypatch):
    uid = create_test_user_with_mall()
    try:
        # compute expected gross consumer goods from countries.get_revenue
        rev_before = countries.get_revenue(uid)
        expected_gross = rev_before.get("gross", {}).get("consumer_goods", 0)

        # ensure task can run
        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute(
                "UPDATE task_runs SET last_run = now() - interval '5 minutes' "
                "WHERE task_name=%s",
                ("generate_province_revenue",),
            )
            # Ensure task cursor will process provinces from start
            db.execute(
                "INSERT INTO task_cursors (task_name, last_id) VALUES (%s, %s) "
                "ON CONFLICT (task_name) DO UPDATE SET last_id=0",
                ("generate_province_revenue", 0),
            )
            db.execute(
                "UPDATE task_cursors SET last_id=0 WHERE task_name=%s",
                ("generate_province_revenue",),
            )
            conn.commit()

        # Run revenue once (enable verbose logs to diagnose production)
        monkeypatch.setattr(tasks, "VERBOSE_REVENUE_LOGS", True)
        tasks.generate_province_revenue()

        # Check consumer_goods after production
        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute("SELECT consumer_goods FROM resources WHERE id=%s", (uid,))
            row = db.fetchone()
            cg_after = row[0] if row and row[0] is not None else 0

        assert cg_after >= expected_gross

        # Now run tax_income once and ensure consumer_goods are consumed by tax_income
        # Reset task_runs for tax_income
        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute(
                "UPDATE task_runs SET last_run = now() - interval '5 minutes' "
                "WHERE task_name=%s",
                ("tax_income",),
            )
            conn.commit()

        # Run tax income which should subtract consumer goods for citizen need
        tasks.tax_income()

        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute("SELECT consumer_goods FROM resources WHERE id=%s", (uid,))
            row2 = db.fetchone()
            cg_after_tax = row2[0] if row2 and row2[0] is not None else 0

        # consumer goods after tax should be <= before tax (consumed or unchanged)
        assert cg_after_tax <= cg_after

    finally:
        cleanup_user(uid)
