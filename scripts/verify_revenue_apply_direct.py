"""Lightweight verification: record coal/lumber before, run the revenue task,
then show deltas for a limited set of candidate users.

Usage:
  python scripts/verify_revenue_apply_direct.py --limit 20

This avoids calling `countries.get_revenue` to keep the run fast and robust
on staging by only reading/writing the necessary resource rows.
"""

import argparse
from database import get_db_connection


def find_candidates(limit=20):
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            """
            SELECT DISTINCT provinces.userId
            FROM proInfra
            INNER JOIN provinces ON proInfra.id = provinces.id
            WHERE (proInfra.coal_mines>0 OR proInfra.lumber_mills>0)
            LIMIT %s
            """,
            (limit,),
        )
        return [row[0] for row in db.fetchall()]


def fetch_resources_bulk(user_ids):
    # Fetch resources for a list of user ids in one query to avoid repeated
    # connection churn and speed up the verification.
    if not user_ids:
        return {}
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            "SELECT id, coal, lumber FROM resources WHERE id = ANY(%s)",
            (list(user_ids),),
        )
        rows = db.fetchall() or []
        result = {}
        for r in rows:
            uid = r[0]
            coal = r[1] or 0
            lumber = r[2] or 0
            result[uid] = {"coal": coal, "lumber": lumber}
        # Ensure all requested ids have an entry
        for uid in user_ids:
            if uid not in result:
                result[uid] = {"coal": 0, "lumber": 0}
        return result


def run_revenue_once():
    import tasks

    tasks.generate_province_revenue()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    candidates = find_candidates(limit=args.limit)
    if not candidates:
        print("No candidate users with coal/lumber production found.")
        return

    before = fetch_resources_bulk(candidates)
    print("Before snapshot:")
    for uid in candidates:
        print({"user_id": uid, **before[uid]})

    print("Running revenue generator (this WILL write DB)")
    run_revenue_once()

    after = fetch_resources_bulk(candidates)
    print("After snapshot and deltas:")
    for uid in candidates:
        b = before[uid]
        a = after[uid]
        print(
            {
                "user_id": uid,
                "coal_before": b["coal"],
                "coal_after": a["coal"],
                "delta_coal": a["coal"] - b["coal"],
                "lumber_before": b["lumber"],
                "lumber_after": a["lumber"],
                "delta_lumber": a["lumber"] - b["lumber"],
            }
        )


if __name__ == "__main__":
    main()
