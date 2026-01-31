#!/usr/bin/env python3
from database import get_db_connection

name = "Lamlor"
out_lines = []
with get_db_connection() as conn:
    db = conn.cursor()
    db.execute(
        "SELECT id, user_id, name FROM countries "
        "WHERE LOWER(name)=LOWER(%s) OR name ILIKE %s LIMIT 5",
        (name, f"%{name}%"),
    )
    crows = db.fetchall()
    out_lines.append(f"countries found: {crows!r}")
    if not crows:
        users_sql = (
            "SELECT id, name, login FROM users "
            "WHERE LOWER(name)=LOWER(%s) OR name ILIKE %s OR login ILIKE %s LIMIT 5"
        )
        db.execute(users_sql, (name, f"%{name}%", f"%{name}%"))
        urows = db.fetchall()
        out_lines.append(f"users found by name/login: {urows!r}")
    else:
        cid, uid, cname = crows[0]
        out_lines.append(f"country id, user_id, name: {cid}, {uid}, {cname!r}")
        db.execute("SELECT id, name, population FROM provinces WHERE userId=%s", (uid,))
        provinces = db.fetchall()
        out_lines.append(f"provinces: {provinces!r}")
        if provinces:
            pids = [p[0] for p in provinces]
            placeholders = ",".join(["%s"] * len(pids))
            proinfra_sql = (
                "SELECT id, gas_stations, general_stores, farmers_markets, "
                "malls, banks FROM proInfra WHERE id IN (" + placeholders + ")"
            )
            db.execute(proinfra_sql, tuple(pids))
            out_lines.append(f"proInfra gas counts: {db.fetchall()!r}")
        revenue_sql = (
            "SELECT id, type, name, resource, amount, date FROM revenue "
            "WHERE user_id=%s ORDER BY date DESC LIMIT 200"
        )
        db.execute(revenue_sql, (uid,))
        rows = db.fetchall()
        out_lines.append(f"recent revenue count: {len(rows)}")
        for r in rows[:50]:
            out_lines.append(f"rev: {r!r}")
        db.execute("SELECT gold FROM stats WHERE id=%s", (uid,))
        out_lines.append(f"gold: {db.fetchone()!r}")
        db.execute("SELECT consumer_goods FROM resources WHERE id=%s", (uid,))
        out_lines.append(f"consumer_goods: {db.fetchone()!r}")
        repairs_sql = (
            "SELECT id, change_type, details, created_at FROM repairs "
            "WHERE user_id=%s ORDER BY created_at DESC LIMIT 20"
        )
        db.execute(repairs_sql, (uid,))
        out_lines.append(f"repairs: {db.fetchall()!r}")

# Write to workspace file for reliable capture
with open("backups/lamlor_audit.txt", "w") as f:
    for line in out_lines:
        f.write(line + "\n")

print("Wrote backups/lamlor_audit.txt")
