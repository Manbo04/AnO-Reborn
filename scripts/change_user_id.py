"""Change a user id across all relevant tables.

Usage:
  PYTHONPATH=. python3 scripts/change_user_id.py --from-id 4908 --to-id 69696969 --apply
  PYTHONPATH=. python3 scripts/change_user_id.py --from-id 4908 --to-id 69696969 --dry-run

Actions:
 - Verify source exists and target doesn't
 - Backup relevant rows into backups/change-userid-<from>-<ts>/
 - Perform atomic updates across tables: users, resources, stats, military, upgrades, policies, offers, trades, wars, spyinfo, provinces, etc.
 - Update sequences if needed
 - Write applied-changes.json with counts
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

BACKUP_DIR_TEMPLATE = "backups/change-userid-{from_id}-{ts}"

TABLE_UPDATES = [
    # (sql_update, params_builder, description)
    ("UPDATE resources SET id=%s WHERE id=%s", lambda f, t: (t, f), "resources id"),
    ("UPDATE stats SET id=%s WHERE id=%s", lambda f, t: (t, f), "stats id"),
    ("UPDATE military SET id=%s WHERE id=%s", lambda f, t: (t, f), "military id"),
    (
        "UPDATE upgrades SET user_id=%s WHERE user_id=%s",
        lambda f, t: (t, f),
        "upgrades user_id",
    ),
    (
        "UPDATE policies SET user_id=%s WHERE user_id=%s",
        lambda f, t: (t, f),
        "policies user_id",
    ),
    (
        "UPDATE offers SET user_id=%s WHERE user_id=%s",
        lambda f, t: (t, f),
        "offers user_id",
    ),
    (
        "UPDATE trades SET offerer=%s WHERE offerer=%s",
        lambda f, t: (t, f),
        "trades.offerer",
    ),
    (
        "UPDATE trades SET offeree=%s WHERE offeree=%s",
        lambda f, t: (t, f),
        "trades.offeree",
    ),
    (
        "UPDATE wars SET attacker=%s WHERE attacker=%s",
        lambda f, t: (t, f),
        "wars.attacker",
    ),
    (
        "UPDATE wars SET defender=%s WHERE defender=%s",
        lambda f, t: (t, f),
        "wars.defender",
    ),
    (
        "UPDATE spyinfo SET spyer=%s WHERE spyer=%s",
        lambda f, t: (t, f),
        "spyinfo.spyer",
    ),
    (
        "UPDATE spyinfo SET spyee=%s WHERE spyee=%s",
        lambda f, t: (t, f),
        "spyinfo.spyee",
    ),
    (
        "UPDATE provinces SET userId=%s WHERE userId=%s",
        lambda f, t: (t, f),
        "provinces.userId",
    ),
    ("UPDATE users SET id=%s WHERE id=%s", lambda f, t: (t, f), "users id"),
]

BACKUP_QUERIES = {
    "users": ("SELECT * FROM users WHERE id=%s", lambda f, t: (f,)),
    "resources": ("SELECT * FROM resources WHERE id=%s", lambda f, t: (f,)),
    "stats": ("SELECT * FROM stats WHERE id=%s", lambda f, t: (f,)),
    "military": ("SELECT * FROM military WHERE id=%s", lambda f, t: (f,)),
    "upgrades": ("SELECT * FROM upgrades WHERE user_id=%s", lambda f, t: (f,)),
    "policies": ("SELECT * FROM policies WHERE user_id=%s", lambda f, t: (f,)),
    "offers": ("SELECT * FROM offers WHERE user_id=%s", lambda f, t: (f,)),
    "trades_offerer": ("SELECT * FROM trades WHERE offerer=%s", lambda f, t: (f,)),
    "trades_offeree": ("SELECT * FROM trades WHERE offeree=%s", lambda f, t: (f,)),
    "wars_attacker": ("SELECT * FROM wars WHERE attacker=%s", lambda f, t: (f,)),
    "wars_defender": ("SELECT * FROM wars WHERE defender=%s", lambda f, t: (f,)),
    "spy_spyer": ("SELECT * FROM spyinfo WHERE spyer=%s", lambda f, t: (f,)),
    "spy_spyee": ("SELECT * FROM spyinfo WHERE spyee=%s", lambda f, t: (f,)),
    "provinces": ("SELECT * FROM provinces WHERE userId=%s", lambda f, t: (f,)),
}


def ensure_dir(d):
    os.makedirs(d, exist_ok=True)


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def backup_rows(cur, outdir, from_id):
    result = {}
    for name, (sql, params_fn) in BACKUP_QUERIES.items():
        cur.execute(sql, params_fn(from_id, None))
        rows = [dict(r) for r in cur.fetchall()]
        result[name] = rows
        write_json(os.path.join(outdir, f"{name}.json"), rows)
    return result


def run_change(conn, cur, from_id, to_id, dry_run=False):
    summary = {"updated": []}

    # Check to avoid accidental overwrite
    cur.execute("SELECT COUNT(*) AS count FROM users WHERE id=%s", (to_id,))
    if cur.fetchone()["count"] > 0:
        raise Exception(f"Target id {to_id} already exists in users table. Aborting.")

    # Perform updates
    for sql, params_fn, desc in TABLE_UPDATES:
        if dry_run:
            cur.execute(sql.replace("%s", "COUNT(*)"), params_fn(from_id, to_id))
            # The above replace is not perfect for complex queries; fallback to count queries
            # Build a count query instead to get the number of affected rows
            # e.g., for UPDATE X SET col=to WHERE col=from -> SELECT COUNT(*) FROM X WHERE col=from
            # We'll infer table and column from desc
            if desc == "users id":
                cur.execute(
                    "SELECT COUNT(*) AS count FROM users WHERE id=%s", (from_id,)
                )
            elif desc == "resources id":
                cur.execute(
                    "SELECT COUNT(*) AS count FROM resources WHERE id=%s", (from_id,)
                )
            elif desc == "stats id":
                cur.execute(
                    "SELECT COUNT(*) AS count FROM stats WHERE id=%s", (from_id,)
                )
            elif desc == "military id":
                cur.execute(
                    "SELECT COUNT(*) AS count FROM military WHERE id=%s", (from_id,)
                )
            elif desc == "provinces.userId":
                cur.execute(
                    "SELECT COUNT(*) AS count FROM provinces WHERE userId=%s",
                    (from_id,),
                )
            elif desc == "upgrades user_id":
                cur.execute(
                    "SELECT COUNT(*) AS count FROM upgrades WHERE user_id=%s",
                    (from_id,),
                )
            elif desc == "policies user_id":
                cur.execute(
                    "SELECT COUNT(*) AS count FROM policies WHERE user_id=%s",
                    (from_id,),
                )
            elif desc == "offers user_id":
                cur.execute(
                    "SELECT COUNT(*) AS count FROM offers WHERE user_id=%s", (from_id,)
                )
            elif desc == "trades.offerer":
                cur.execute(
                    "SELECT COUNT(*) AS count FROM trades WHERE offerer=%s", (from_id,)
                )
            elif desc == "trades.offeree":
                cur.execute(
                    "SELECT COUNT(*) AS count FROM trades WHERE offeree=%s", (from_id,)
                )
            elif desc == "wars.attacker":
                cur.execute(
                    "SELECT COUNT(*) AS count FROM wars WHERE attacker=%s", (from_id,)
                )
            elif desc == "wars.defender":
                cur.execute(
                    "SELECT COUNT(*) AS count FROM wars WHERE defender=%s", (from_id,)
                )
            elif desc == "spyinfo.spyer":
                cur.execute(
                    "SELECT COUNT(*) AS count FROM spyinfo WHERE spyer=%s", (from_id,)
                )
            elif desc == "spyinfo.spyee":
                cur.execute(
                    "SELECT COUNT(*) AS count FROM spyinfo WHERE spyee=%s", (from_id,)
                )
            else:
                cur.execute("SELECT 0 AS count")
            count = cur.fetchone()["count"]
            summary["updated"].append({"op": desc, "count": count, "dry_run": True})
        else:
            cur.execute(sql, params_fn(from_id, to_id))
            summary["updated"].append({"op": desc, "rows_affected": cur.rowcount})

    # Update users sequence if needed
    if not dry_run:
        # Try to set users_id_seq to max(id)+1 if exists
        try:
            cur.execute(
                "SELECT setval('users_id_seq', GREATEST((SELECT MAX(id) FROM users), %s)+1, false)",
                (to_id,),
            )
        except Exception:
            # Sequence may have a different name or not exist; ignore
            pass

    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-id", type=int, required=True)
    parser.add_argument("--to-id", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true", default=False)
    parser.add_argument("--apply", action="store_true", default=False)
    args = parser.parse_args()

    if args.dry_run and args.apply:
        print("Cannot use both --dry-run and --apply")
        return
    if not args.dry_run and not args.apply:
        # default to apply since user asked to apply
        args.apply = True

    from_id = args.from_id
    to_id = args.to_id

    outdir = BACKUP_DIR_TEMPLATE.format(from_id=from_id, ts=TS)
    ensure_dir(outdir)

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
                # Verify source exists
                cur.execute("SELECT * FROM users WHERE id=%s", (from_id,))
                user = cur.fetchone()
                if not user:
                    print(f"Source user id {from_id} not found. Aborting.")
                    return
                print(
                    "Found user:", {"id": user["id"], "username": user.get("username")}
                )

                # Check target free
                cur.execute("SELECT COUNT(*) AS count FROM users WHERE id=%s", (to_id,))
                if cur.fetchone()["count"] > 0:
                    print(f"Target id {to_id} already exists. Aborting.")
                    return

                # Backup rows
                print("Creating backups in:", outdir)
                backup = backup_rows(cur, outdir, from_id)
                write_json(
                    os.path.join(outdir, "prechange-summary.json"),
                    {"from": from_id, "to": to_id, "tables": list(backup.keys())},
                )

                if args.dry_run:
                    print("Dry-run: previewing changes")
                    summary = run_change(conn, cur, from_id, to_id, dry_run=True)
                    write_json(os.path.join(outdir, "dryrun-changes.json"), summary)
                    print(json.dumps(summary, indent=2))
                    return

                print(f"Applying id change {from_id} -> {to_id}")
                summary = run_change(conn, cur, from_id, to_id, dry_run=False)
                write_json(os.path.join(outdir, "applied-changes.json"), summary)
                print("Change applied. Backups in:", outdir)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
