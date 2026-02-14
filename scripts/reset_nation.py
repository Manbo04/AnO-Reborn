"""Reset a single nation to starting defaults (resources, provinces, infra, military, upgrades, policies, market rows).

Usage examples:
  PYTHONPATH=. python3 scripts/reset_nation.py --user-id 33 --apply
  PYTHONPATH=. python3 scripts/reset_nation.py --user-id 33 --dry-run

The script will:
 - Create a timestamped backup directory with CSV/JSON of pre-change rows
 - In a single transaction, apply the reset changes
 - If --dry-run is used, it will print what it WOULD do without committing
 - Always writes an audit JSON of before/after state to the backup dir

This script is intended to be safe and reversible (backups kept).
"""

import argparse
import os
import json
import time
import csv
from datetime import datetime
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

load_dotenv()

DEFAULTS = {
    "resources": {
        "rations": 800,
        "lumber": 400,
        "steel": 250,
        "aluminium": 200,
        "oil": 0,
        "coal": 0,
        "uranium": 0,
        "bauxite": 0,
        "lead": 0,
        "copper": 0,
        "components": 0,
        "consumer_goods": 0,
        "gasoline": 0,
        "ammunition": 0,
    },
    "stats": {"gold": 20000000},
    "military": {"manpower": 100, "defcon": 1},
    "province": {
        "population": 1000000,
        "citycount": 1,
        "land": 1,
        "energy": 0,
        "happiness": 50,
        "pollution": 0,
        "productivity": 50,
        "consumer_spending": 50,
    },
}

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


def backup_rows(cur, outdir, user_id):
    # Tables and SQL to fetch rows related to the user
    queries = {
        "users": ("SELECT * FROM users WHERE id=%s", (user_id,)),
        "resources": ("SELECT * FROM resources WHERE id=%s", (user_id,)),
        "stats": ("SELECT * FROM stats WHERE id=%s", (user_id,)),
        "military": ("SELECT * FROM military WHERE id=%s", (user_id,)),
        "upgrades": ("SELECT * FROM upgrades WHERE user_id=%s", (user_id,)),
        "policies": ("SELECT * FROM policies WHERE user_id=%s", (user_id,)),
        "offers": ("SELECT * FROM offers WHERE user_id=%s", (user_id,)),
        "trades": (
            "SELECT * FROM trades WHERE offerer=%s OR offeree=%s",
            (user_id, user_id),
        ),
        "wars": (
            "SELECT * FROM wars WHERE attacker=%s OR defender=%s",
            (user_id, user_id),
        ),
        "spyinfo": (
            "SELECT * FROM spyinfo WHERE spyer=%s OR spyee=%s",
            (user_id, user_id),
        ),
        "provinces": ("SELECT * FROM provinces WHERE userId=%s", (user_id,)),
        "proInfra": (
            "SELECT * FROM proInfra WHERE id IN (SELECT id FROM provinces WHERE userId=%s)",
            (user_id,),
        ),
    }

    backup = {}
    for name, (sql, params) in queries.items():
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
        backup[name] = rows
        write_json(os.path.join(outdir, f"{name}.json"), rows)
        write_csv(os.path.join(outdir, f"{name}.csv"), rows)
    return backup


def apply_reset(conn, cur, user_id, dry_run=False):
    changes = {"updated": [], "deleted": []}

    # Resources: upsert to defaults
    res = DEFAULTS["resources"].copy()
    cols = ", ".join(res.keys())
    vals = ", ".join(["%s"] * len(res))
    upsert_q = (
        f"INSERT INTO resources (id, {cols}) VALUES (%s, {vals}) "
        f"ON CONFLICT (id) DO UPDATE SET "
        + ", ".join([f"{k}=EXCLUDED.{k}" for k in res.keys()])
    )
    params = [user_id] + [res[k] for k in res.keys()]
    if dry_run:
        cur.execute("SELECT COUNT(*) FROM resources WHERE id=%s", (user_id,))
        row = cur.fetchone()
        exists = row["count"] if row and "count" in row else 0
        changes["updated"].append(
            {"table": "resources", "exists": bool(exists), "values": res}
        )
    else:
        cur.execute(upsert_q, params)
        changes["updated"].append({"table": "resources", "values": res})

    # Stats
    st = DEFAULTS["stats"].copy()
    # stats.location is NOT NULL in schema; preserve existing location if present
    if dry_run:
        changes["updated"].append({"table": "stats", "values": st})
    else:
        cur.execute("SELECT location FROM stats WHERE id=%s", (user_id,))
        row = cur.fetchone()
        if row and row.get("location") is not None:
            cur.execute("UPDATE stats SET gold=%s WHERE id=%s", (st["gold"], user_id))
        else:
            # Insert with empty location to satisfy NOT NULL constraint
            cur.execute(
                "INSERT INTO stats (id, location, gold) VALUES (%s, %s, %s)",
                (user_id, "", st["gold"]),
            )

    # Military
    mil_defaults = {
        "manpower": DEFAULTS["military"]["manpower"],
        "defcon": DEFAULTS["military"]["defcon"],
    }
    zero_units = [
        "soldiers",
        "artillery",
        "tanks",
        "bombers",
        "fighters",
        "apaches",
        "spies",
        "ICBMs",
        "nukes",
        "destroyers",
        "cruisers",
        "submarines",
    ]
    if dry_run:
        changes["updated"].append(
            {"table": "military", "set": {**mil_defaults, **{u: 0 for u in zero_units}}}
        )
    else:
        # Ensure a row exists
        cur.execute(
            "INSERT INTO military (id, manpower, defcon) VALUES (%s, %s, %s) ON CONFLICT (id) DO UPDATE SET manpower=EXCLUDED.manpower, defcon=EXCLUDED.defcon",
            (user_id, mil_defaults["manpower"], mil_defaults["defcon"]),
        )
        # Zero out units
        upd = ", ".join([f"{u}=0" for u in zero_units])
        cur.execute(f"UPDATE military SET {upd} WHERE id=%s", (user_id,))
        changes["updated"].append(
            {"table": "military", "set": {**mil_defaults, **{u: 0 for u in zero_units}}}
        )

    # Upgrades: set all flags to 0 (if table has row, update; else insert)
    # Retrieve columns for upgrades
    cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name='upgrades' AND column_name<>'user_id'"
    )
    cols = [r["column_name"] for r in cur.fetchall()]
    upgrades_set = {c: 0 for c in cols}
    if dry_run:
        changes["updated"].append({"table": "upgrades", "values": upgrades_set})
    else:
        # Check if row exists
        cur.execute("SELECT COUNT(*) FROM upgrades WHERE user_id=%s", (user_id,))
        row = cur.fetchone()
        count = int(row["count"]) if row and "count" in row else 0
        if count == 0:
            # Insert a row
            cols_str = ",".join(["user_id"] + list(upgrades_set.keys()))
            vals = ",".join(["%s"] * (1 + len(upgrades_set)))
            params = [user_id] + [0] * len(upgrades_set)
            cur.execute(f"INSERT INTO upgrades ({cols_str}) VALUES ({vals})", params)
        else:
            set_str = ",".join([f"{c}=%s" for c in upgrades_set.keys()])
            params = [0] * len(upgrades_set) + [user_id]
            cur.execute(f"UPDATE upgrades SET {set_str} WHERE user_id=%s", params)
        changes["updated"].append({"table": "upgrades", "values": upgrades_set})

    # Policies: reset to empty arrays/defaults if table exists
    cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name='policies' AND column_name<>'user_id'"
    )
    policy_cols = [r["column_name"] for r in cur.fetchall()]
    pol_defaults = {c: "{}" for c in policy_cols}
    if dry_run:
        changes["updated"].append({"table": "policies", "values": pol_defaults})
    else:
        cur.execute("SELECT COUNT(*) FROM policies WHERE user_id=%s", (user_id,))
        row = cur.fetchone()
        count = int(row["count"]) if row and "count" in row else 0
        if count == 0:
            cols_str = ",".join(["user_id"] + policy_cols)
            vals = ",".join(["%s"] * (1 + len(policy_cols)))
            params = [user_id] + ["{}"] * len(policy_cols)
            cur.execute(f"INSERT INTO policies ({cols_str}) VALUES ({vals})", params)
        else:
            set_str = ",".join([f"{c}=%s" for c in policy_cols])
            params = ["{}"] * len(policy_cols) + [user_id]
            cur.execute(f"UPDATE policies SET {set_str} WHERE user_id=%s", params)
        changes["updated"].append({"table": "policies", "values": pol_defaults})

    # Provinces + proInfra: reset all provinces belonging to user to defaults
    cur.execute("SELECT id FROM provinces WHERE userId=%s", (user_id,))
    provs = [r["id"] for r in cur.fetchall()]
    prov_changes = []
    for pid in provs:
        prov_defaults = DEFAULTS["province"].copy()
        if dry_run:
            prov_changes.append({"province_id": pid, "values": prov_defaults})
        else:
            cur.execute(
                "UPDATE provinces SET population=%s, citycount=%s, land=%s, energy=%s, happiness=%s, pollution=%s, productivity=%s, consumer_spending=%s WHERE id=%s",
                (
                    prov_defaults["population"],
                    prov_defaults["citycount"],
                    prov_defaults["land"],
                    prov_defaults["energy"],
                    prov_defaults["happiness"],
                    prov_defaults["pollution"],
                    prov_defaults["productivity"],
                    prov_defaults["consumer_spending"],
                    pid,
                ),
            )
            # Zero all proInfra columns for this province id
            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name='proinfra' AND column_name<>'id'"
            )
            infra_cols = [r["column_name"] for r in cur.fetchall()]
            if infra_cols:
                set_str = ",".join([f"{c}=0" for c in infra_cols])
                cur.execute(f"UPDATE proInfra SET {set_str} WHERE id=%s", (pid,))
            prov_changes.append({"province_id": pid, "values": prov_defaults})
    if prov_changes:
        changes["updated"].append(
            {"table": "provinces/proInfra", "provinces": prov_changes}
        )

    # Offers/Trades/Wars/Spyinfo: delete rows involving user
    if dry_run:
        cur.execute("SELECT COUNT(*) FROM offers WHERE user_id=%s", (user_id,))
        row = cur.fetchone()
        offers_n = int(row["count"]) if row and "count" in row else 0
        cur.execute(
            "SELECT COUNT(*) FROM trades WHERE offerer=%s OR offeree=%s",
            (user_id, user_id),
        )
        row = cur.fetchone()
        trades_n = int(row["count"]) if row and "count" in row else 0
        cur.execute(
            "SELECT COUNT(*) FROM wars WHERE attacker=%s OR defender=%s",
            (user_id, user_id),
        )
        row = cur.fetchone()
        wars_n = int(row["count"]) if row and "count" in row else 0
        cur.execute(
            "SELECT COUNT(*) FROM spyinfo WHERE spyer=%s OR spyee=%s",
            (user_id, user_id),
        )
        row = cur.fetchone()
        spy_n = int(row["count"]) if row and "count" in row else 0
        changes["deleted"].append(
            {"offers": offers_n, "trades": trades_n, "wars": wars_n, "spyinfo": spy_n}
        )
    else:
        cur.execute("DELETE FROM offers WHERE user_id=%s", (user_id,))
        cur.execute(
            "DELETE FROM trades WHERE offerer=%s OR offeree=%s", (user_id, user_id)
        )
        cur.execute(
            "DELETE FROM wars WHERE attacker=%s OR defender=%s", (user_id, user_id)
        )
        cur.execute(
            "DELETE FROM spyinfo WHERE spyer=%s OR spyee=%s", (user_id, user_id)
        )
        changes["deleted"].append(
            {
                "offers": "deleted",
                "trades": "deleted",
                "wars": "deleted",
                "spyinfo": "deleted",
            }
        )

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
    # If neither specified, default to apply (user requested immediate)
    if not apply_now and not dry_run:
        apply_now = True

    OUTDIR = f"backups/reset-nation-{user_id}-{TS}"
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
                print("Creating backup of current rows for user", user_id)
                backup = backup_rows(cur, OUTDIR, user_id)
                write_json(
                    os.path.join(OUTDIR, "prechange-summary.json"),
                    {"user_id": user_id, "backup_tables": list(backup.keys())},
                )

                if dry_run:
                    print("Dry-run: previewing changes (no commit).")
                    changes = apply_reset(conn, cur, user_id, dry_run=True)
                    write_json(os.path.join(OUTDIR, "dryrun-changes.json"), changes)
                    print(json.dumps(changes, indent=2))
                    print("Dry-run complete. No changes applied.")
                    return

                print("Applying reset transaction for user", user_id)
                changes = apply_reset(conn, cur, user_id, dry_run=False)
                write_json(os.path.join(OUTDIR, "applied-changes.json"), changes)
                print("Reset applied successfully. Created backups in:", OUTDIR)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
