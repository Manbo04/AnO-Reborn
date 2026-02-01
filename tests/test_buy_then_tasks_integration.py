from database import get_db_connection
import variables
import tasks


def test_buy_then_tasks_sequence():
    with get_db_connection() as conn:
        db = conn.cursor()
        # create user
        db.execute(
            "INSERT INTO users (username, email, date, hash) VALUES (%s,%s,%s,%s) "
            "RETURNING id",
            ("seq_test", "seq@example.com", "2026-01-01", ""),
        )
        uid = db.fetchone()[0]
        db.execute(
            "INSERT INTO provinces (userId, provincename, citycount, land, population) "
            "VALUES (%s,%s,%s,%s,%s) RETURNING id",
            (uid, "Seq", 1, 1, 240000),
        )
        pid = db.fetchone()[0]
        db.execute("INSERT INTO proInfra (id) VALUES (%s)", (pid,))
        db.execute(
            "INSERT INTO stats (id, location, gold) VALUES (%s,%s,%s) "
            "ON CONFLICT (id) DO UPDATE SET location=%s, gold=%s",
            (uid, "Seq", 2000000, "Seq", 2000000),
        )
        db.execute(
            "INSERT INTO resources (id, consumer_goods, rations) VALUES (%s,%s,%s) "
            "ON CONFLICT (id) DO UPDATE SET consumer_goods=%s, rations=%s",
            (uid, 0, 0, 0, 0),
        )
        conn.commit()

        # perform buy via direct updates (reuse province logic)
        purchase_price = variables.PROVINCE_UNIT_PRICES["gas_stations_price"] * 2
        db.execute("SELECT gold FROM stats WHERE id=%s", (uid,))
        before_gold = db.fetchone()[0]
        db.execute(
            "UPDATE stats SET gold = gold - %s WHERE id=%s", (purchase_price, uid)
        )
        db.execute(
            "UPDATE proInfra SET gas_stations = gas_stations + %s WHERE id=%s", (2, pid)
        )
        conn.commit()

        # run tasks
        # reset last_run
        db.execute(
            "UPDATE task_runs SET last_run = now() - interval '1 day' "
            "WHERE task_name IN ('generate_province_revenue','tax_income')"
        )
        conn.commit()
        tasks.generate_province_revenue()
        tasks.tax_income()

        db.execute("SELECT gold FROM stats WHERE id=%s", (uid,))
        after_gold = db.fetchone()[0]
        # After purchase, tasks may add revenue, but net <= pre-purchase amount.
        assert after_gold <= before_gold

        # Cleanup
        db.execute("DELETE FROM purchase_audit WHERE user_id=%s", (uid,))
        db.execute("DELETE FROM revenue WHERE user_id=%s", (uid,))
        db.execute("DELETE FROM proInfra WHERE id=%s", (pid,))
        db.execute("DELETE FROM provinces WHERE id=%s", (pid,))
        db.execute("DELETE FROM stats WHERE id=%s", (uid,))
        db.execute("DELETE FROM resources WHERE id=%s", (uid,))
        db.execute("DELETE FROM users WHERE id=%s", (uid,))
        conn.commit()
