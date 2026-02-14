"""Set users sequence to the first free id >= a given start value.

Usage:
  PYTHONPATH=. python3 scripts/set_users_seq_first_free.py --start 500 --apply
  PYTHONPATH=. python3 scripts/set_users_seq_first_free.py --start 500 --dry-run

This script:
 - Scans existing ids >= start, finds the smallest missing integer >= start
 - Sets users sequence to that integer using setval(seq, candidate, false)
 - Writes audit to backups/set-users-seq-firstfree-<ts>/audit.json

It is safe to run; if the desired candidate is already taken by a race, it will recompute and retry.
"""

import argparse
import os
import json
from datetime import datetime
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

load_dotenv()
TS = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
OUTDIR_TEMPLATE = "backups/set-users-seq-firstfree-{ts}"


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def find_first_free(cur, start):
    # Fetch ascending ids >= start
    cur.execute("SELECT id FROM users WHERE id >= %s ORDER BY id", (start,))
    rows = [r["id"] for r in cur.fetchall()]
    candidate = start
    for id_val in rows:
        if id_val == candidate:
            candidate += 1
            continue
        if id_val > candidate:
            break
    return candidate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true", default=False)
    parser.add_argument("--apply", action="store_true", default=False)
    args = parser.parse_args()

    if args.dry_run and args.apply:
        print("Cannot use both --dry-run and --apply")
        return
    if not args.dry_run and not args.apply:
        args.apply = True

    start = args.start
    outdir = OUTDIR_TEMPLATE.format(ts=TS)
    os.makedirs(outdir, exist_ok=True)

    conn = psycopg2.connect(
        dbname=os.getenv("PG_DATABASE"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        host=os.getenv("PG_HOST", "localhost"),
        port=os.getenv("PG_PORT", "5432"),
    )
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT pg_get_serial_sequence('users','id') AS seqname")
                seqrow = cur.fetchone()
                seqname = seqrow.get("seqname") if seqrow else None

                cur_val = None
                if seqname:
                    try:
                        cur.execute(f"SELECT last_value, is_called FROM {seqname}")
                        cur_val = cur.fetchone()
                    except Exception as e:
                        cur_val = {"error": str(e)}

                candidate = find_first_free(cur, start)

                audit = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "start": start,
                    "seqname": seqname,
                    "current_seq_val": cur_val,
                    "candidate": candidate,
                }
                write_json(os.path.join(outdir, "audit-pre.json"), audit)

                if args.dry_run:
                    print("Dry-run: first free candidate is", candidate)
                    print(json.dumps(audit, indent=2))
                    return

                # Final check & set - ensure candidate still free
                cur.execute(
                    "SELECT COUNT(*) AS cnt FROM users WHERE id=%s", (candidate,)
                )
                if cur.fetchone()["cnt"] > 0:
                    # race: recompute and pick next
                    candidate = find_first_free(cur, candidate + 1)

                cur.execute("SELECT setval(%s, %s, false)", (seqname, candidate))
                cur.execute(f"SELECT last_value, is_called FROM {seqname}")
                after = cur.fetchone()
                audit["applied_seq_val"] = after
                write_json(os.path.join(outdir, "audit-applied.json"), audit)
                print("Sequence set to next:", candidate, "audit:", outdir)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
