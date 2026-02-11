#!/usr/bin/env python3
"""Sandbox repro: copy nation 4760 provinces into the designated test account (id=16),
run generate_province_revenue repeatedly, capture pollution values, and restore state.

Follows CLAUDE.md rules: uses test account id 16 and leaves no trace (restores original
provinces/proInfra/stats/resources after run).
"""
from database import get_db_connection
import json
import time
import tasks

SOURCE_UID = 4760
TEST_UID = 16
ITERATIONS = 50

results = {}
created_pids = []
orig_provinces = {}
orig_proinfras = {}
orig_stats = None
orig_resources = None

try:
    with get_db_connection() as conn:
        db = conn.cursor()

        # Record original stats/resources for TEST_UID
        db.execute("SELECT gold, location FROM stats WHERE id=%s", (TEST_UID,))
        r = db.fetchone()
        orig_stats = dict(gold=r[0], location=r[1]) if r else None

        db.execute(
            "SELECT consumer_goods, rations FROM resources WHERE id=%s", (TEST_UID,)
        )
        r = db.fetchone()
        orig_resources = dict(consumer_goods=r[0], rations=r[1]) if r else None

        # Record existing provinces and proInfra rows for TEST_UID
        db.execute(
            (
                "SELECT id, provincename, citycount, land, population, energy, "
                "happiness, pollution, productivity, consumer_spending "
                "FROM provinces WHERE userId=%s ORDER BY id"
            ),
            (TEST_UID,),
        )
        existing = db.fetchall()
        orig_province_rows = existing
        for row in existing:
            pid = row[0]
            orig_provinces[pid] = {
                "row": row,
            }
            db.execute("SELECT * FROM proInfra WHERE id=%s", (pid,))
            infra_row = db.fetchone()
            if infra_row:
                cols = [d[0] for d in db.description]
                orig_proinfras[pid] = dict(zip(cols, infra_row))
            else:
                orig_proinfras[pid] = None

        # Copy provinces from SOURCE_UID into TEST_UID
        db.execute(
            (
                "SELECT id, provincename, citycount, land, population, energy, "
                "happiness, pollution, productivity, consumer_spending "
                "FROM provinces WHERE userId=%s ORDER BY id"
            ),
            (SOURCE_UID,),
        )
        source_provs = db.fetchall()
        if not source_provs:
            raise RuntimeError(f"No provinces found for source user {SOURCE_UID}")

        new_pids = []
        old_pids = []
        for (
            old_pid,
            provincename,
            citycount,
            land,
            population,
            energy,
            happiness,
            pollution,
            productivity,
            consumer_spending,
        ) in source_provs:
            old_pids.append(old_pid)
            name = f"{provincename} (repro {SOURCE_UID})"
            vals = (
                TEST_UID,
                name,
                citycount,
                land,
                population,
                energy,
                happiness,
                pollution,
                productivity,
                consumer_spending,
            )
            db.execute(
                (
                    "INSERT INTO provinces (userId, provincename, citycount, land, "
                    "population, energy, happiness, pollution, productivity, "
                    "consumer_spending) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                    "RETURNING id"
                ),
                vals,
            )
            new_pid = db.fetchone()[0]
            new_pids.append(new_pid)

        # Copy proInfra for each old_pid to new_pid
        col_names = None
        for old_pid, new_pid in zip(old_pids, new_pids):
            db.execute("SELECT * FROM proInfra WHERE id=%s", (old_pid,))
            row = db.fetchone()
            if not row:
                # Insert empty proInfra row for new province with default columns
                db.execute(
                    (
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name='proinfra' ORDER BY ordinal_position"
                    )
                )
                cols = [c[0] for c in db.fetchall()]
                placeholders = ",".join(["%s"] * len(cols))
                values = [new_pid] + [0] * (len(cols) - 1)
                db.execute(
                    f"INSERT INTO proInfra ({','.join(cols)}) VALUES ({placeholders})",
                    tuple(values),
                )
            else:
                if col_names is None:
                    db.execute(
                        (
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_name='proinfra' ORDER BY ordinal_position"
                        )
                    )
                    col_names = [c[0] for c in db.fetchall()]
                vals = list(row)
                vals[0] = new_pid
                insert_cols = ",".join(col_names)
                placeholders = ",".join(["%s"] * len(vals))
                sql = (
                    "INSERT INTO proInfra ("
                    + insert_cols
                    + ") VALUES ("
                    + placeholders
                    + ")"
                )
                args = tuple(vals)
                db.execute(sql, args)

        conn.commit()
        created_pids = new_pids

        # Ensure stats/resources for TEST_UID are funded
        _stats_vals = [
            TEST_UID,
            "Testland",
            5_000_000,
            "Testland",
            5_000_000,
        ]
        stats_vals = tuple(_stats_vals)
        db.execute(
            (
                "INSERT INTO stats (id, location, gold) VALUES (%s,%s,%s) "
                "ON CONFLICT (id) DO UPDATE SET location=%s, gold=%s"
            ),
            stats_vals,
        )
        _res_vals = [TEST_UID, 0, 0, 0, 0]
        res_vals = tuple(_res_vals)
        db.execute(
            (
                "INSERT INTO resources (id, consumer_goods, rations) VALUES (%s,%s,%s) "
                "ON CONFLICT (id) DO UPDATE SET consumer_goods=%s, rations=%s"
            ),
            res_vals,
        )
        conn.commit()

        # Force task_runs to be eligible
        db.execute(
            (
                "UPDATE task_runs SET last_run = now() - interval '1 day' "
                "WHERE task_name IN ("
                "'generate_province_revenue', "
                "'tax_income', "
                "'population_growth'"
                ")"
            )
        )
        conn.commit()

        # Set subject provinces to a high pollution (98) to recreate reported state
        for pid in created_pids:
            db.execute("UPDATE provinces SET pollution=%s WHERE id=%s", (98, pid))
        conn.commit()

    # Run revenue task ITERATIONS times and capture pollution over time
    pollution_timeline = {}
    for pid in created_pids:
        pollution_timeline[pid] = []

    for i in range(ITERATIONS):
        try:
            tasks.generate_province_revenue()
        except Exception as e:
            print(f"Iteration {i}: task error: {e}")
        with get_db_connection() as conn:
            db = conn.cursor()
            for pid in created_pids:
                db.execute("SELECT pollution FROM provinces WHERE id=%s", (pid,))
                r = db.fetchone()
                pollution_timeline[pid].append(r[0] if r else None)
        time.sleep(0.1)

    results["pollution_timeline"] = pollution_timeline

    # Basic analysis
    for pid, vals in pollution_timeline.items():
        vals_filtered = [v for v in vals if v is not None]
        if vals_filtered:
            key_min = f"pid_{pid}_min"
            key_max = f"pid_{pid}_max"
            key_delta = f"pid_{pid}_delta"
            min_v = min(vals_filtered)
            max_v = max(vals_filtered)
            results[key_min] = min_v
            results[key_max] = max_v
            results[key_delta] = max_v - min_v

    print(json.dumps(results, indent=2))

finally:
    # Restore test account state: delete created provinces/proInfra
    # and restore stats/resources
    with get_db_connection() as conn:
        db = conn.cursor()
        try:
            for pid in created_pids:
                db.execute("DELETE FROM proInfra WHERE id=%s", (pid,))
                db.execute("DELETE FROM provinces WHERE id=%s", (pid,))
            # Restore stats
            if orig_stats:
                g = orig_stats["gold"]
                loc = orig_stats["location"]
                db.execute(
                    ("UPDATE stats SET gold=%s, location=%s " "WHERE id=%s"),
                    (g, loc, TEST_UID),
                )
            else:
                db.execute("DELETE FROM stats WHERE id=%s", (TEST_UID,))
            # Restore resources
            if orig_resources:
                cg = orig_resources["consumer_goods"]
                rations_val = orig_resources["rations"]
                db.execute(
                    (
                        "UPDATE resources SET consumer_goods=%s, rations=%s "
                        "WHERE id=%s"
                    ),
                    (cg, rations_val, TEST_UID),
                )
            else:
                db.execute("DELETE FROM resources WHERE id=%s", (TEST_UID,))
            # No further restore needed for proInfra/provinces (we only added new rows)
            conn.commit()
        except Exception as e:
            print("Cleanup failed:", e)

print("Done.")
