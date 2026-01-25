"""Verify all users have the expected starting resource values.
Writes a short report to stdout and to /tmp/verify_reset_values.txt
"""

from database import get_db_cursor

EXPECTED = {
    "rations": 10000,
    "lumber": 2000,
    "steel": 2000,
    "aluminium": 2000,
    "oil": 500,
    "coal": 500,
    "uranium": 500,
    "bauxite": 500,
    "lead": 500,
    "copper": 500,
    "iron": 500,
    "components": 500,
}

out_lines = []
with get_db_cursor() as db:
    db.execute("SELECT COUNT(*) FROM users")
    total_users = db.fetchone()[0]

    params = tuple(
        EXPECTED[col]
        for col in (
            "rations",
            "lumber",
            "steel",
            "aluminium",
            "oil",
            "coal",
            "uranium",
            "bauxite",
            "lead",
            "copper",
            "iron",
            "components",
        )
    )
    db.execute(
        (
            "SELECT COUNT(*) FROM resources WHERE rations=%s AND lumber=%s AND "
            "steel=%s AND aluminium=%s AND oil=%s AND coal=%s AND uranium=%s "
            "AND bauxite=%s AND lead=%s AND copper=%s AND iron=%s AND components=%s"
        ),
        params,
    )
    matching = db.fetchone()[0]

    out_lines.append(f"TOTAL_USERS: {total_users}")
    out_lines.append(f"MATCHING_USERS: {matching}")

    # find up to 10 users that do NOT match exactly
    db.execute(
        (
            "SELECT u.id, u.username, r.rations, r.lumber, r.steel, r.aluminium, "
            "r.oil, r.coal, r.uranium, r.bauxite, "
            "r.lead, r.copper, r.iron, r.components "
            "FROM users u JOIN resources r ON u.id=r.id WHERE NOT ("
            "r.rations=%s AND r.lumber=%s AND r.steel=%s AND r.aluminium=%s AND "
            "r.oil=%s AND r.coal=%s AND r.uranium=%s AND r.bauxite=%s AND r.lead=%s "
            "AND r.copper=%s AND r.iron=%s AND r.components=%s) LIMIT 10"
        ),
        params,
    )
    mismatches = db.fetchall()
    out_lines.append("MISMATCHES_FOUND: %d (show up to 10)" % (len(mismatches)))
    for m in mismatches:
        out_lines.append(str(m))

    # offers checks for preserved users
    db.execute(
        "SELECT id,username FROM users WHERE username = ANY(%s)",
        (["Market Bot", "Supply Bot"],),
    )
    preserved = db.fetchall()
    preserved_ids = [p[0] for p in preserved]
    db.execute("SELECT COUNT(*) FROM offers")
    out_lines.append(f"TOTAL_OFFERS: {db.fetchone()[0]}")
    db.execute("SELECT COUNT(*) FROM offers WHERE user_id = ANY(%s)", (preserved_ids,))
    out_lines.append(f"OFFERS_PRESERVED: {db.fetchone()[0]}")

report = "\n".join(out_lines)
print(report)
with open("/tmp/verify_reset_values.txt", "w") as f:
    f.write(report)
