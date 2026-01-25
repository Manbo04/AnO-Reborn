"""Reset player progress to starting values (non-destructive by default).

Usage:
  # dry-run: show counts and examples
  PYTHONPATH=. venv310/bin/python scripts/reset_progress.py --dry-run

  # execute actual reset (will modify DB)
  PYTHONPATH=. venv310/bin/python scripts/reset_progress.py --execute --preserve-market-users bot_user

Notes:
 - By default this script excludes users with role='admin' from resets.
 - To preserve market bot offers, pass --preserve-market-users with a comma-separated
   list of usernames (or set env MARKET_PRESERVE_USERS="bot1,bot2").
 - The script will:
   * Reset resources and stats to configured starting values
   * Remove provinces and infrastructure
   * Reset military units to defaults
   * Clean market offers/trades excluding preserved users

This is destructive when run with --execute. Make sure you have a DB backup before running.
"""

import argparse
import os
from typing import List
from database import get_db_cursor

# Defaults used in other scripts (kept consistent)
DEFAULTS = {
    "rations": 800,
    "lumber": 400,
    "steel": 250,
    "aluminium": 200,
    "gold": 20000000,
    "military_manpower": 100,
    "defcon": 1,
}


def parse_preserve_list(val: str) -> List[str]:
    if not val:
        return []
    return [v.strip() for v in val.split(",") if v.strip()]


def run(
    dry_run: bool = True,
    preserve_market_users: List[str] = None,
    exclude_admins: bool = True,
):
    preserve_market_users = preserve_market_users or []
    exclude_clause = " AND u.role != 'admin'" if exclude_admins else ""

    with get_db_cursor() as db:
        # Find user ids to operate on
        db.execute(f"SELECT id, username FROM users u WHERE 1=1{exclude_clause}")
        users = db.fetchall()
        user_ids = [u[0] for u in users]
        print(
            f"Total users considered for reset: {len(user_ids)} (exclude_admins={exclude_admins})"
        )

        # Resolve preserve user_ids for market
        preserved_ids = []
        if preserve_market_users:
            db.execute(
                "SELECT id, username FROM users WHERE username = ANY(%s)",
                (preserve_market_users,),
            )
            preserved = db.fetchall()
            preserved_ids = [p[0] for p in preserved]
            print(
                f"Preserving market offers for users: {[p[1] for p in preserved]} (ids: {preserved_ids})"
            )

        if dry_run:
            # Show sample counts
            db.execute("SELECT COUNT(*) FROM provinces")
            provinces_count = db.fetchone()[0]
            db.execute("SELECT COUNT(*) FROM offers")
            offers_count = db.fetchone()[0]
            print(f"Provinces total: {provinces_count}")
            print(f"Market offers total: {offers_count}")
            print("Would reset resources and stats for all non-admin users.")
            print("Would delete all provinces and infrastructures.")
            if preserved_ids:
                db.execute(
                    "SELECT COUNT(*) FROM offers WHERE user_id != ALL(%s)",
                    (preserved_ids,),
                )
                offers_to_delete = db.fetchone()[0]
                print(f"Offers to delete (excluding preserved): {offers_to_delete}")
            else:
                db.execute("SELECT COUNT(*) FROM offers")
                print(f"Offers to delete: {db.fetchone()[0]}")
            return

        # Execute real reset
        print("Starting destructive reset...")

        # Military reset
        units = [
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
        for unit in units:
            db.execute(
                f"UPDATE military SET {unit}=0 WHERE id = ANY(%s){exclude_clause}",
                (user_ids,),
            )
        db.execute(
            "UPDATE military SET manpower=%s WHERE id = ANY(%s)%s",
            (DEFAULTS["military_manpower"], user_ids, exclude_clause),
        )
        db.execute(
            "UPDATE military SET defcon=%s WHERE id = ANY(%s)%s",
            (DEFAULTS["defcon"], user_ids, exclude_clause),
        )

        # Resources reset
        resources = [
            "oil",
            "coal",
            "uranium",
            "bauxite",
            "lead",
            "copper",
            "iron",
            "components",
            "consumer_goods",
            "gasoline",
            "ammunition",
        ]
        for resource in resources:
            db.execute(
                f"UPDATE resources SET {resource}=0 WHERE id = ANY(%s){exclude_clause}",
                (user_ids,),
            )
        db.execute(
            "UPDATE resources SET rations=%s WHERE id = ANY(%s)%s",
            (DEFAULTS["rations"], user_ids, exclude_clause),
        )
        db.execute(
            "UPDATE resources SET lumber=%s WHERE id = ANY(%s)%s",
            (DEFAULTS["lumber"], user_ids, exclude_clause),
        )
        db.execute(
            "UPDATE resources SET steel=%s WHERE id = ANY(%s)%s",
            (DEFAULTS["steel"], user_ids, exclude_clause),
        )
        db.execute(
            "UPDATE resources SET aluminium=%s WHERE id = ANY(%s)%s",
            (DEFAULTS["aluminium"], user_ids, exclude_clause),
        )

        # Stats/gold
        db.execute(
            "UPDATE stats SET gold=%s WHERE id = ANY(%s)%s",
            (DEFAULTS["gold"], user_ids, exclude_clause),
        )

        # Provinces and infra
        db.execute("SELECT id FROM provinces")
        provinces = [r[0] for r in db.fetchall()]
        if provinces:
            db.execute("DELETE FROM proInfra WHERE id = ANY(%s)", (provinces,))
            db.execute("DELETE FROM provinces")
            print(f"Deleted {len(provinces)} provinces and their infra")

        # Market cleanup: remove offers/trades except from preserved users
        if preserved_ids:
            db.execute("DELETE FROM offers WHERE user_id != ALL(%s)", (preserved_ids,))
            db.execute(
                "DELETE FROM trades WHERE (offerer != ALL(%s) AND offeree != ALL(%s))",
                (preserved_ids, preserved_ids),
            )
        else:
            db.execute("DELETE FROM offers")
            db.execute("DELETE FROM trades")
        print("Market cleaned (preserved users kept their offers/trades if specified)")

        # Commit
        print("Committing changes...")

    print("Reset completed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--preserve-market-users", default=os.getenv("MARKET_PRESERVE_USERS", "")
    )
    parser.add_argument(
        "--exclude-admins", dest="exclude_admins", action="store_true", default=True
    )
    args = parser.parse_args()

    preserve = parse_preserve_list(args.preserve_market_users)
    run(
        dry_run=not args.execute,
        preserve_market_users=preserve,
        exclude_admins=args.exclude_admins,
    )
