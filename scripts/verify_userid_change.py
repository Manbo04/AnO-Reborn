"""Verify user id change from from_id to to_id across tables and report issues.

Usage: PYTHONPATH=. python3 scripts/verify_userid_change.py --from-id 4908 --to-id 69696969
"""
import argparse
import os
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
import json

load_dotenv()

TABLE_CHECKS = [
    ("users", "id"),
    ("resources", "id"),
    ("stats", "id"),
    ("military", "id"),
    ("upgrades", "user_id"),
    ("policies", "user_id"),
    ("offers", "user_id"),
    ("trades", "offerer"),
    ("trades", "offeree"),
    ("wars", "attacker"),
    ("wars", "defender"),
    ("spyinfo", "spyer"),
    ("spyinfo", "spyee"),
    ("provinces", "userId"),
]


def check_counts(cur, table, col, from_id, to_id):
    cur.execute(
        f"SELECT COUNT(*) AS count_from FROM {table} WHERE {col}=%s", (from_id,)
    )
    from_cnt = cur.fetchone()["count_from"]
    cur.execute(f"SELECT COUNT(*) AS count_to FROM {table} WHERE {col}=%s", (to_id,))
    to_cnt = cur.fetchone()["count_to"]
    return from_cnt, to_cnt


def check_sequence(cur):
    # Try to find sequence for users.id
    cur.execute("SELECT pg_get_serial_sequence('users','id') AS seqname")
    row = cur.fetchone()
    seq = row.get("seqname") if row else None
    seq_val = None
    if seq:
        try:
            cur.execute(f"SELECT last_value, is_called FROM {seq}")
            s = cur.fetchone()
            seq_val = s
        except Exception as e:
            seq_val = str(e)
    return seq, seq_val


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-id", type=int, required=True)
    parser.add_argument("--to-id", type=int, required=True)
    args = parser.parse_args()

    from_id = args.from_id
    to_id = args.to_id

    conn = psycopg2.connect(
        dbname=os.getenv("PG_DATABASE"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        host=os.getenv("PG_HOST", "localhost"),
        port=os.getenv("PG_PORT", "5432"),
    )
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            print(f"Verifying id change: {from_id} -> {to_id}\n")
            issues = []
            report = {}
            for table, col in TABLE_CHECKS:
                try:
                    from_cnt, to_cnt = check_counts(cur, table, col, from_id, to_id)
                    report[f"{table}.{col}"] = {
                        "from_count": int(from_cnt),
                        "to_count": int(to_cnt),
                    }
                    if from_cnt != 0:
                        issues.append(
                            f"{table}.{col} still has {from_cnt} rows with old id {from_id}"
                        )
                except Exception as e:
                    report[f"{table}.{col}"] = {"error": str(e)}
                    issues.append(f"Error checking {table}.{col}: {e}")

            seq_name, seq_val = check_sequence(cur)
            report["users_sequence"] = {"seq_name": seq_name, "seq_val": seq_val}

            print(json.dumps(report, indent=2, default=str))
            if issues:
                print("\nISSUES FOUND:\n" + "\n".join(issues))
            else:
                print("\nNo issues found: all checks passed.")

            # Show backup applied-changes.json if present
            backups_dir = f"backups/change-userid-{from_id}-*"
            import glob

            matches = glob.glob(f"backups/change-userid-{from_id}-*")
            if matches:
                latest = sorted(matches)[-1]
                fpath = os.path.join(latest, "applied-changes.json")
                if os.path.exists(fpath):
                    print("\nApplied changes summary from backup:")
                    with open(fpath, "r", encoding="utf-8") as f:
                        print(f.read())
                else:
                    print(f"\nNo applied-changes.json found in {latest}")
            else:
                print(f"\nNo backups found for user {from_id}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
