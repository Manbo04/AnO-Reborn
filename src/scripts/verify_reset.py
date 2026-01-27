from src.database import get_db_cursor

with get_db_cursor() as db:
    db.execute("SELECT COUNT(*) FROM provinces")
    provinces = db.fetchone()[0]

    db.execute("SELECT COUNT(*) FROM offers")
    offers_total = db.fetchone()[0]

    db.execute(
        "SELECT id,username FROM users WHERE username = ANY(%s)",
        (["Market Bot", "Supply Bot"],),
    )
    preserved = db.fetchall()
    preserved_ids = [p[0] for p in preserved]

    db.execute("SELECT COUNT(*) FROM offers WHERE user_id = ANY(%s)", (preserved_ids,))
    offers_preserved = db.fetchone()[0]

    db.execute(
        "SELECT id FROM users WHERE username NOT IN ('Market Bot','Supply Bot') LIMIT 1"
    )
    r = db.fetchone()
    if r:
        sample = r[0]
        db.execute(
            "SELECT rations,lumber,steel,aluminium FROM resources WHERE id=%s",
            (sample,),
        )
        resources_sample = db.fetchone()
        db.execute("SELECT gold FROM stats WHERE id=%s", (sample,))
        gold_sample = db.fetchone()[0]
        db.execute("SELECT manpower,defcon FROM military WHERE id=%s", (sample,))
        military_sample = db.fetchone()
    else:
        sample = None
        resources_sample = None
        gold_sample = None
        military_sample = None

print("PROVINCES_COUNT:", provinces)
print("OFFERS_TOTAL:", offers_total)
print("PRESERVED_USERS:", preserved)
print("OFFERS_PRESERVED:", offers_preserved)
print("SAMPLE_USER_ID:", sample)
print("RESOURCE_SAMPLE:", resources_sample)
print("GOLD_SAMPLE:", gold_sample)
print("MILITARY_SAMPLE:", military_sample)
