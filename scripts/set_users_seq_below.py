"""Set users_id_seq next value to (MAX(id) where id < threshold) + 1.

Usage:
  PYTHONPATH=. python3 scripts/set_users_seq_below.py --threshold 69696969 --apply
  PYTHONPATH=. python3 scripts/set_users_seq_below.py --threshold 69696969 --dry-run

Writes audit to backups/set-users-seq-below-<ts>/seq-audit.json
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
OUTDIR = f"backups/set-users-seq-below-{TS}"
os.makedirs(OUTDIR, exist_ok=True)


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true", default=False)
    parser.add_argument("--apply", action="store_true", default=False)
    args = parser.parse_args()

    if args.dry_run and args.apply:
        print("Cannot use both --dry-run and --apply")
        return
    if not args.dry_run and not args.apply:
        args.apply = True

    thr = args.threshold

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
                row = cur.fetchone()
                seqname = row.get("seqname") if row else None

                # get current seq val
                cur_val = None
                if seqname:
                    try:
                        cur.execute(f"SELECT last_value, is_called FROM {seqname}")
                        cur_val = cur.fetchone()
                    except Exception as e:
                        cur_val = {"error": str(e)}

                cur.execute(
                    "SELECT MAX(id) AS max_below FROM users WHERE id < %s", (thr,)
                )
                row = cur.fetchone()
                max_below = row.get("max_below") if row and "max_below" in row else None
                if max_below is None:
                    max_below = 0
                new_next = int(max_below) + 1

                audit = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "threshold": thr,
                    "seqname": seqname,
                    "current_seq_val": cur_val,
                    "computed_max_below": max_below,
                    "new_next": new_next,
                }
                write_json(os.path.join(OUTDIR, "seq-audit-pre.json"), audit)

                if args.dry_run:
                    print("Dry-run audit:")
                    print(json.dumps(audit, indent=2))
                    return

                if not seqname:
                    print("Sequence name not found; aborting")
                    write_json(
                        os.path.join(OUTDIR, "seq-error.json"),
                        {"error": "sequence not found"},
                    )
                    return

                cur.execute("SELECT setval(%s, %s, false)", (seqname, new_next))
                cur.execute(f"SELECT last_value, is_called FROM {seqname}")
                after = cur.fetchone()
                audit["applied_seq_val"] = after
                write_json(os.path.join(OUTDIR, "seq-audit-applied.json"), audit)
                print("Sequence updated to next:", new_next, "audit at", OUTDIR)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
