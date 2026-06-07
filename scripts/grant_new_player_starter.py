#!/usr/bin/env python3
"""Grant starter resources + gold to a user (compensation / backfill).

Usage:
  python3 scripts/grant_new_player_starter.py --user-id 69697588
  python3 scripts/grant_new_player_starter.py --username "Unknown Identity"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from signup import _init_economy_tables  # noqa: E402
from database import get_db_connection  # noqa: E402

STARTER_GOLD = 80_000_000


def resolve_user_id(db, user_id: int | None, username: str | None) -> int:
    if user_id:
        db.execute("SELECT id FROM users WHERE id = %s", (user_id,))
        row = db.fetchone()
        if not row:
            raise SystemExit(f"User id {user_id} not found")
        return int(user_id)
    if username:
        db.execute("SELECT id FROM users WHERE username ILIKE %s", (username,))
        row = db.fetchone()
        if not row:
            raise SystemExit(f"Username {username!r} not found")
        return int(row[0])
    raise SystemExit("Provide --user-id or --username")


def main() -> None:
    parser = argparse.ArgumentParser(description="Grant new-player starter package")
    parser.add_argument("--user-id", type=int, default=None)
    parser.add_argument("--username", type=str, default=None)
    parser.add_argument("--gold-only", action="store_true")
    args = parser.parse_args()

    with get_db_connection() as conn:
        db = conn.cursor()
        uid = resolve_user_id(db, args.user_id, args.username)
        db.execute(
            "UPDATE stats SET gold = GREATEST(COALESCE(gold, 0), %s) WHERE id = %s",
            (STARTER_GOLD, uid),
        )
        if not args.gold_only:
            _init_economy_tables(db, uid)
        conn.commit()
        print(f"Granted starter package to user_id={uid}")


if __name__ == "__main__":
    main()
