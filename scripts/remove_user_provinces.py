"""Delete all provinces (and corresponding proInfra) belonging to a single user.

Usage examples:
  PYTHONPATH=. python3 scripts/remove_user_provinces.py --user-id 33 --dry-run
  PYTHONPATH=. python3 scripts/remove_user_provinces.py --user-id 33 --apply

The script will:
 - Create a timestamped backup directory with JSON/CSV of provinces and proInfra rows
 - In a single transaction, delete proInfra rows for those province ids
   and delete provinces rows for user
 - If --dry-run is used, it will print what it WOULD do without committing
 - Always writes an audit JSON of before/after state to the backup dir
"""

import argparse
import os
import json
import csv
from datetime import datetime
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

load_dotenv()
TS = datetime.utcnow().strftime("%Y%m%d-%H%M%S")


def ensure_backup_dir(outdir):
    os.makedirs(outdir, exist_ok=True)


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def write_csv(path, rows):
    if not rows:
        return
    keys = rows[0].keys()
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def backup_and_delete(conn, cur, user_id, dry_run=False):
    # Fetch provinces for user
    cur.execute("SELECT * FROM provinces WHERE userId=%s", (user_id,))
    provinces = [dict(r) for r in cur.fetchall()]
    prov_ids = [p["id"] for p in provinces]

    cur.execute(
        "SELECT * FROM proInfra WHERE id = ANY(%s)",
        (prov_ids if prov_ids else [None],),
    )
    proinfra = [dict(r) for r in cur.fetchall()]

    changes = {"provinces_count": len(provinces), "proinfra_count": len(proinfra)}

    if dry_run:
        return {"dry_run": True, **changes}

    # SAFETY CHECK: Prevent accidental deletes in production unless explicitly enabled
    # To allow irreversible deletions in production set the
    # environment variable ALLOW_PROVINCE_DELETION=true
    env = os.getenv("ENVIRONMENT", "DEV").upper()
    allow_flag = os.getenv("ALLOW_PROVINCE_DELETION", "false").lower()
    if env == "PROD" and allow_flag != "true":
        raise RuntimeError(
            "Refusing to delete provinces in PROD without "
            "ALLOW_PROVINCE_DELETION=true"
        )

    # Ensure admin_actions table exists for auditing
    try:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_actions (
                id SERIAL PRIMARY KEY,
                actor TEXT,
                action TEXT,
                user_id INTEGER,
                details JSONB,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
            )
            """
        )
    except Exception:
        # Best-effort: do not fail deletion solely because audit table
        # couldn't be created
        pass

    # Insert audit record before destructive action
    try:
        cur.execute(
            (
                "INSERT INTO admin_actions (actor, action, user_id, details) "
                "VALUES (%s,%s,%s,%s)"
            ),
            (
                os.getenv("USER") or os.getenv("GITHUB_ACTOR") or "script",
                "delete_provinces",
                user_id,
                json.dumps(
                    {"provinces_count": len(provinces), "proinfra_count": len(proinfra)}
                ),
            ),
        )
    except Exception:
        # best-effort audit
        pass

    # perform deletions in transaction
    if prov_ids:
        cur.execute("DELETE FROM proInfra WHERE id = ANY(%s)", (prov_ids,))
    cur.execute("DELETE FROM provinces WHERE userId=%s", (user_id,))

    return changes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true", default=False)
    parser.add_argument("--apply", action="store_true", default=False)
    args = parser.parse_args()

    user_id = args.user_id
    dry_run = args.dry_run
    apply_now = args.apply

    if apply_now and dry_run:
        print("Cannot use both --dry-run and --apply at the same time. Exiting.")
        return
    if not apply_now and not dry_run:
        apply_now = True

    OUTDIR = f"backups/remove-provinces-{user_id}-{TS}"
    ensure_backup_dir(OUTDIR)

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
                # Backup current provinces and proInfra
                cur.execute("SELECT * FROM provinces WHERE userId=%s", (user_id,))
                provinces = [dict(r) for r in cur.fetchall()]
                write_json(os.path.join(OUTDIR, "provinces.json"), provinces)
                write_csv(os.path.join(OUTDIR, "provinces.csv"), provinces)

                prov_ids = [p["id"] for p in provinces]
                if prov_ids:
                    cur.execute(
                        "SELECT * FROM proInfra WHERE id = ANY(%s)", (prov_ids,)
                    )
                    proinfra = [dict(r) for r in cur.fetchall()]
                else:
                    proinfra = []
                write_json(os.path.join(OUTDIR, "proInfra.json"), proinfra)
                write_csv(os.path.join(OUTDIR, "proInfra.csv"), proinfra)

                write_json(
                    os.path.join(OUTDIR, "prechange-summary.json"),
                    {
                        "provinces_count": len(provinces),
                        "proinfra_count": len(proinfra),
                    },
                )

                if dry_run:
                    print(
                        "Dry-run: would delete these provinces/proInfra:",
                        json.dumps(
                            {
                                "provinces_count": len(provinces),
                                "proinfra_count": len(proinfra),
                            },
                            indent=2,
                        ),
                    )
                    write_json(
                        os.path.join(OUTDIR, "dryrun-changes.json"),
                        {
                            "dry_run": True,
                            "provinces_count": len(provinces),
                            "proinfra_count": len(proinfra),
                        },
                    )
                    return

                # Apply deletion
                print(
                    (
                        "Deleting {} proInfra rows and {} provinces for user {}".format(
                            len(proinfra), len(provinces), user_id
                        )
                    )
                )
                changes = backup_and_delete(conn, cur, user_id, dry_run=False)
                write_json(os.path.join(OUTDIR, "applied-changes.json"), changes)
                print("Deletion applied; backups created in:", OUTDIR)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
