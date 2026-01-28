"""Verification helper: find accounts producing coal/lumber and optionally run one
hour revenue pass to confirm resources are persisted.

Usage examples:
  # Dry-run: show candidates and before/expected values
  python scripts/verify_revenue_generation.py --limit 3

  # Apply one revenue generation run and show deltas
  python scripts/verify_revenue_generation.py --limit 3 --apply

Notes:
  - Run this on staging or a safe environment
    where `DATABASE_URL` is set (e.g., Railway).
  - When run with `--apply` the script performs writes by
    invoking the revenue task.
"""

import argparse
from database import get_db_connection
from psycopg2.extras import RealDictCursor


def find_candidates(limit=3):
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


def fetch_user_snapshot(user_id):
    with get_db_connection() as conn:
        dbdict = conn.cursor(cursor_factory=RealDictCursor)
        dbdict.execute("SELECT coal, lumber FROM resources WHERE id=%s", (user_id,))
        resources = dbdict.fetchone() or {}
        # Use countries.get_revenue to compute gross production
        import countries

        rev = countries.get_revenue(str(user_id))
        gross_coal = rev.get("gross", {}).get("coal", 0)
        gross_lumber = rev.get("gross", {}).get("lumber", 0)
        return {
            "user_id": user_id,
            "coal": resources.get("coal", 0),
            "lumber": resources.get("lumber", 0),
            "gross_coal": gross_coal,
            "gross_lumber": gross_lumber,
        }


def run_revenue_once():
    import tasks

    tasks.generate_province_revenue()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    candidates = find_candidates(limit=args.limit)
    if not candidates:
        print("No candidate users with coal/lumber production found.")
        return

    snapshots_before = [fetch_user_snapshot(uid) for uid in candidates]
    print("Before:")
    for s in snapshots_before:
        print(s)

    if args.apply:
        print("Running one revenue generation pass (this will write DB)")
        run_revenue_once()
        snapshots_after = [fetch_user_snapshot(uid) for uid in candidates]
        print("After:")
        for b, a in zip(snapshots_before, snapshots_after):
            delta_coal = a["coal"] - b["coal"]
            delta_lumber = a["lumber"] - b["lumber"]
            print(
                {
                    "user_id": a["user_id"],
                    "coal_before": b["coal"],
                    "coal_after": a["coal"],
                    "delta_coal": delta_coal,
                    "expected_coal": b["gross_coal"],
                    "lumber_before": b["lumber"],
                    "lumber_after": a["lumber"],
                    "delta_lumber": delta_lumber,
                    "expected_lumber": b["gross_lumber"],
                }
            )
    else:
        print("Run with --apply to perform one revenue pass and verify deltas.")


if __name__ == "__main__":
    main()
