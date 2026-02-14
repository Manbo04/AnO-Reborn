"""Set users_id_seq back to previous next value (based on max id excluding specified new id).

Usage:
  PYTHONPATH=. python3 scripts/reset_users_sequence.py --exclude-id 69696969 --apply
  PYTHONPATH=. python3 scripts/reset_users_sequence.py --exclude-id 69696969 --dry-run

This will:
 - Compute prev_max = MAX(id) WHERE id != exclude_id
 - Set users sequence to prev_max+1 (using setval(seq, prev_max+1, false)) so next nextval gives prev_max+1
 - Record previous sequence value and new value to backups/reset-users-seq-<ts>/seq-audit.json
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
OUTDIR = f"backups/reset-users-seq-{TS}"

os.makedirs(OUTDIR, exist_ok=True)


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exclude-id", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true", default=False)
    parser.add_argument("--apply", action="store_true", default=False)
    args = parser.parse_args()

    if args.dry_run and args.apply:
        print("Cannot use both --dry-run and --apply")
        return
    if not args.dry_run and not args.apply:
        args.apply = True

    exclude = args.exclude_id

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
                # Determine sequence name
                cur.execute("SELECT pg_get_serial_sequence('users','id') AS seqname")
                row = cur.fetchone()
                seqname = row.get("seqname") if row else None

                # Current seq value
                seq_val = None
                if seqname:
                    try:
                        cur.execute(f"SELECT last_value, is_called FROM {seqname}")
                        seq_val = cur.fetchone()
                    except Exception as e:
                        seq_val = {"error": str(e)}

                # Compute prev_max excluding the big id
                cur.execute(
                    "SELECT MAX(id) AS max_id FROM users WHERE id != %s", (exclude,)
                )
                row = cur.fetchone()
                prev_max = row.get("max_id") or 0

                new_val = int(prev_max) + 1

                audit = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "exclude_id": exclude,
                    "seqname": seqname,
                    "previous_seq_val": seq_val,
                    "computed_prev_max": prev_max,
                    "new_seq_next": new_val,
                }
                write_json(os.path.join(OUTDIR, "seq-audit-pre.json"), audit)

                if args.dry_run:
                    print("Dry-run audit:")
                    print(json.dumps(audit, indent=2, default=str))
                    return

                if not seqname:
                    print("Sequence name not found for users.id; aborting")
                    write_json(
                        os.path.join(OUTDIR, "seq-audit-error.json"),
                        {"error": "sequence not found"},
                    )
                    return

                cur.execute(f"SELECT setval(%s, %s, false)", (seqname, new_val))
                cur.execute(f"SELECT last_value, is_called FROM {seqname}")
                after = cur.fetchone()
                audit["applied_seq_val"] = after
                write_json(os.path.join(OUTDIR, "seq-audit-applied.json"), audit)
                print("Sequence updated. Audit written to", OUTDIR)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
