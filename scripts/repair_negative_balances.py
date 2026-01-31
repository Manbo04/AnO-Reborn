"""Conservative repair script:
- Detect stats.gold < 0 and set to 0, recording a repair row
- Detect any negative resource columns and set those to 0, recording repair rows
- Safe: logs each change to `repairs` table and prints a summary

Usage: PYTHONPATH=. python scripts/repair_negative_balances.py
"""

from database import get_db_connection
import json

if __name__ == "__main__":
    report = {
        "negative_gold": [],
        "negative_resources": [],
    }
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT id, gold FROM stats WHERE gold < 0")
        report["negative_gold"] = db.fetchall()

        db.execute(
            "SELECT id, oil, rations, coal, uranium, bauxite, iron, lead, copper, "
            "lumber, components, steel, consumer_goods, "
            "aluminium, gasoline, ammunition "
            "FROM resources WHERE (oil<0 OR rations<0 OR coal<0 OR uranium<0 OR "
            "bauxite<0 OR iron<0 OR lead<0 OR copper<0 OR lumber<0 OR components<0 OR "
            "steel<0 OR consumer_goods<0 OR aluminium<0 OR gasoline<0 OR ammunition<0)"
        )
        report["negative_resources"] = db.fetchall()

    print("AUDIT REPORT:")
    print(json.dumps(report, indent=2, default=str))

    if not report["negative_gold"] and not report["negative_resources"]:
        print("\nNo negative balances found, nothing to repair.")
        exit(0)

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            (
                "CREATE TABLE IF NOT EXISTS repairs (",
                "id SERIAL PRIMARY KEY, user_id INT, change_type TEXT, details JSONB,",
                "created_at TIMESTAMP WITH TIME ZONE DEFAULT now())",
            )
        )

        # handle negative gold
        db.execute("SELECT id, gold FROM stats WHERE gold < 0")
        neg_golds = db.fetchall()
        for uid, gold in neg_golds:
            details = {
                "before_gold": gold,
                "after_gold": 0,
                "reason": "negative balance auto-repair",
            }
            db.execute(
                "INSERT INTO repairs (user_id, change_type, details) "
                "VALUES (%s,%s,%s)",
                (uid, "negative_gold_reset", json.dumps(details)),
            )
        db.execute("UPDATE stats SET gold = 0 WHERE gold < 0")

        # handle negative resources
        sql = (
            "SELECT id, oil, rations, coal, uranium, bauxite, iron, lead, copper, "
            "lumber, components, steel, consumer_goods, "
            "aluminium, gasoline, ammunition "
            "FROM resources WHERE (oil<0 OR rations<0 OR coal<0 OR uranium<0 OR "
            "bauxite<0 OR iron<0 OR lead<0 OR copper<0 OR lumber<0 OR components<0 OR "
            "steel<0 OR consumer_goods<0 OR aluminium<0 OR gasoline<0 OR ammunition<0)"
        )
        db.execute(sql)
        neg_res_rows = db.fetchall()
        for row in neg_res_rows:
            uid = row[0]
            cols = [
                "oil",
                "rations",
                "coal",
                "uranium",
                "bauxite",
                "iron",
                "lead",
                "copper",
                "lumber",
                "components",
                "steel",
                "consumer_goods",
                "aluminium",
                "gasoline",
                "ammunition",
            ]
            changes = {}
            for i, val in enumerate(row[1:]):
                if val is not None and val < 0:
                    changes[cols[i]] = {"before": val, "after": 0}
            if changes:
                details = {
                    "changes": changes,
                    "reason": "negative resource auto-repair",
                }
                db.execute(
                    "INSERT INTO repairs (user_id, change_type, details) "
                    "VALUES (%s,%s,%s)",
                    (uid, "negative_resources_reset", json.dumps(details)),
                )

        # zero out negative resource columns
        db.execute(
            (
                "UPDATE resources SET ",
                "oil = GREATEST(oil, 0), rations = GREATEST(rations,0), ",
                "coal = GREATEST(coal,0), uranium = GREATEST(uranium,0), ",
                "bauxite = GREATEST(bauxite,0), iron = GREATEST(iron,0), ",
                "lead = GREATEST(lead,0), copper = GREATEST(copper,0), ",
                "lumber = GREATEST(lumber,0), components = GREATEST(components,0), ",
                "steel = GREATEST(steel,0),",
                "consumer_goods = GREATEST(consumer_goods,0),",
                "aluminium = GREATEST(aluminium,0), gasoline = GREATEST(gasoline,0),",
                "ammunition = GREATEST(ammunition,0)",
            )
        )

        # summary
        db.execute("SELECT COUNT(*) FROM stats WHERE gold < 0")
        remaining_neg_gold = db.fetchone()[0]
        sql = (
            "SELECT COUNT(*) FROM resources WHERE (oil<0 OR rations<0 OR coal<0 OR "
            "uranium<0 OR bauxite<0 OR iron<0 OR lead<0 OR copper<0 OR lumber<0 OR "
            "components<0 OR steel<0 OR ",
            "consumer_goods<0 OR aluminium<0 OR gasoline<0 OR " "ammunition<0)",
        )
        db.execute(sql)
        remaining_neg_res = db.fetchone()[0]

    print("Repair applied. Verifying...")
    print("remaining_negative_gold:", remaining_neg_gold)
    print("remaining_negative_resources:", remaining_neg_res)
