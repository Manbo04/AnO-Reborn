#!/usr/bin/env python3
from database import get_db_connection
import variables
import json

# Create a temporary copy of Lamlor (user 781), buy 3 gas stations in first province,
# run generate_province_revenue and tax_income, capture before/after, then clean up.

LAMLOR_UID = 781
WANTED_UNITS = 3
RESULTS = {}
new_uid = None

import datetime

try:
    with get_db_connection() as conn:
        db = conn.cursor()
        # Create temp user (username limited to 60 chars; date is short YYYY-MM-DD)
        today = datetime.date.today().isoformat()
        db.execute(
            "INSERT INTO users (username, email, date, hash) VALUES (%s,%s,%s,%s) RETURNING id",
            ("lamlor_t", "lamlor_test@example.com", today, ""),
        )
        new_uid = db.fetchone()[0]
        print("Created test user id", new_uid)

        # Copy provinces
        db.execute(
            "SELECT id, provincename, citycount, land, population, energy, happiness, pollution, productivity, consumer_spending FROM provinces WHERE userId=%s",
            (LAMLOR_UID,),
        )
        provinces = db.fetchall()
        new_pids = []
        for (
            pid,
            provincename,
            citycount,
            land,
            population,
            energy,
            happiness,
            pollution,
            productivity,
            consumer_spending,
        ) in provinces:
            db.execute(
                (
                    "INSERT INTO provinces (userId, provincename, citycount, land, population, energy, happiness, pollution, productivity, consumer_spending) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id"
                ),
                (
                    new_uid,
                    provincename + " (test)",
                    citycount,
                    land,
                    population,
                    energy,
                    happiness,
                    pollution,
                    productivity,
                    consumer_spending,
                ),
            )
            new_pid = db.fetchone()[0]
            new_pids.append(new_pid)
        print("Created provinces:", new_pids)

        # Copy proInfra rows
        for old_pid, new_pid in zip([p[0] for p in provinces], new_pids):
            db.execute("SELECT * FROM proInfra WHERE id=%s", (old_pid,))
            row = db.fetchone()
            if not row:
                # Insert empty proInfra row for new province
                cols = ["id"] + list(variables.BUILDINGS)
                placeholders = ",".join(["%s"] * len(cols))
                values = [new_pid] + [0] * (len(cols) - 1)
                db.execute(
                    f"INSERT INTO proInfra ({','.join(cols)}) VALUES ({placeholders})",
                    tuple(values),
                )
            else:
                # Row exists and returned as tuple with id first; map to columns
                # We'll select column names dynamically
                db.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_name='proinfra' ORDER BY ordinal_position"
                )
                col_names = [c[0] for c in db.fetchall()]
                vals = list(row)
                # replace id with new_pid
                vals[0] = new_pid
                insert_cols = ",".join(col_names)
                placeholders = ",".join(["%s"] * len(vals))
                db.execute(
                    f"INSERT INTO proInfra ({insert_cols}) VALUES ({placeholders})",
                    tuple(vals),
                )
        print("Copied/created proInfra rows")

        # Ensure stats/resources rows
        db.execute(
            "INSERT INTO stats (id, location, gold) VALUES (%s,%s,%s) ON CONFLICT (id) DO UPDATE SET location=%s, gold = %s",
            (new_uid, "Testland", 5_000_000, "Testland", 5_000_000),
        )
        db.execute(
            "INSERT INTO resources (id, consumer_goods, rations) VALUES (%s,%s,%s) ON CONFLICT (id) DO UPDATE SET consumer_goods=%s, rations=%s",
            (new_uid, 0, 0, 0, 0),
        )

        conn.commit()

        # Capture before
        db.execute("SELECT gold FROM stats WHERE id=%s", (new_uid,))
        RESULTS["gold_before"] = db.fetchone()[0]
        db.execute("SELECT consumer_goods FROM resources WHERE id=%s", (new_uid,))
        RESULTS["consumer_goods_before"] = db.fetchone()[0]

        import countries

        rev_before = countries.get_revenue(new_uid)
        RESULTS["revenue_before"] = rev_before
        print(
            "Before: gold",
            RESULTS["gold_before"],
            "cg",
            RESULTS["consumer_goods_before"],
        )

        # Simulate buy: purchase WANTED_UNITS gas stations in first province
        purchase_price = (
            variables.PROVINCE_UNIT_PRICES["gas_stations_price"] * WANTED_UNITS
        )
        target_pid = new_pids[0]
        db.execute(
            "UPDATE stats SET gold = gold - %s WHERE id=%s", (purchase_price, new_uid)
        )
        db.execute(
            "UPDATE proInfra SET gas_stations = gas_stations + %s WHERE id=%s",
            (WANTED_UNITS, target_pid),
        )
        db.execute(
            "INSERT INTO revenue (user_id, type, name, description, date, resource, amount) VALUES (%s,%s,%s,%s, now()::date, %s, %s)",
            (
                new_uid,
                "expense",
                f"Buying {WANTED_UNITS} gas_stations in a province.",
                "",
                "gas_stations",
                WANTED_UNITS,
            ),
        )
        conn.commit()

        # Capture after buy, before tasks
        db.execute("SELECT gold FROM stats WHERE id=%s", (new_uid,))
        RESULTS["gold_after_buy"] = db.fetchone()[0]
        db.execute("SELECT gas_stations FROM proInfra WHERE id=%s", (target_pid,))
        RESULTS["gas_stations_after_buy"] = db.fetchone()[0]
        print(
            "After buy: gold",
            RESULTS["gold_after_buy"],
            "gas_stations",
            RESULTS["gas_stations_after_buy"],
        )

        # Allow tasks to run: reset last_run to past
        db.execute(
            "UPDATE task_runs SET last_run = now() - interval '1 day' WHERE task_name IN ('generate_province_revenue','tax_income')"
        )
        conn.commit()

        # Run tasks
        import tasks

        tasks.generate_province_revenue()
        tasks.tax_income()

        # Capture after tasks
        db.execute("SELECT gold FROM stats WHERE id=%s", (new_uid,))
        RESULTS["gold_after_tasks"] = db.fetchone()[0]
        db.execute("SELECT consumer_goods FROM resources WHERE id=%s", (new_uid,))
        RESULTS["consumer_goods_after_tasks"] = db.fetchone()[0]
        rev_after = countries.get_revenue(new_uid)
        RESULTS["revenue_after"] = rev_after

        print(
            "After tasks: gold",
            RESULTS["gold_after_tasks"],
            "cg",
            RESULTS["consumer_goods_after_tasks"],
        )

finally:
    # Cleanup: remove created rows
    with get_db_connection() as conn:
        db = conn.cursor()
        try:
            db.execute("DELETE FROM revenue WHERE user_id=%s", (new_uid,))
            for pid in new_pids:
                db.execute("DELETE FROM proInfra WHERE id=%s", (pid,))
                db.execute("DELETE FROM provinces WHERE id=%s", (pid,))
            db.execute("DELETE FROM stats WHERE id=%s", (new_uid,))
            db.execute("DELETE FROM resources WHERE id=%s", (new_uid,))
            db.execute("DELETE FROM repairs WHERE user_id=%s", (new_uid,))
            db.execute("DELETE FROM users WHERE id=%s", (new_uid,))
            conn.commit()
        except Exception as e:
            print("Cleanup failed:", e)

# Print summary
print(json.dumps(RESULTS, indent=2, default=str))
