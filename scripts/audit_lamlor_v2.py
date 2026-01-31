#!/usr/bin/env python3
from database import get_db_connection

uid = 781
out = []
with get_db_connection() as conn:
    db = conn.cursor()
    db.execute(
        "SELECT id, provincename, population FROM provinces WHERE userId=%s", (uid,)
    )
    provinces = db.fetchall()
    out.append(("provinces", provinces))
    if provinces:
        pids = [p[0] for p in provinces]
        placeholders = ",".join(["%s"] * len(pids))
        proinfra_sql = (
            "SELECT id, gas_stations, general_stores, "
            "farmers_markets, malls, banks FROM proInfra "
            f"WHERE id IN ({placeholders})"
        )
        db.execute(proinfra_sql, tuple(pids))
        out.append(("proInfra", db.fetchall()))
    revenue_sql = (
        "SELECT id, type, name, resource, amount, date FROM revenue "
        "WHERE user_id=%s ORDER BY date DESC LIMIT 200"
    )
    db.execute(revenue_sql, (uid,))
    rows = db.fetchall()
    out.append(("recent_revenue_count", len(rows)))
    out.append(("recent_revenue_rows", rows[:200]))
    db.execute("SELECT gold FROM stats WHERE id=%s", (uid,))
    out.append(("gold", db.fetchone()))
    db.execute("SELECT consumer_goods FROM resources WHERE id=%s", (uid,))
    out.append(("consumer_goods", db.fetchone()))
    repairs_sql = (
        "SELECT id, change_type, details, created_at FROM repairs "
        "WHERE user_id=%s ORDER BY created_at DESC LIMIT 50"
    )
    db.execute(repairs_sql, (uid,))
    out.append(("repairs", db.fetchall()))

with open("backups/lamlor_details.txt", "w") as f:
    for k, v in out:
        f.write(f"{k}: {v!r}\n")

print("wrote backups/lamlor_details.txt")
