#!/usr/bin/env python3
"""Insert a devlog entry directly (bypasses the /devlog admin web form).

Used by the weekly Discord announcement automation to mirror the same
recap into the in-game Devlog panel. See app_core/community/repositories.py
for the web-facing equivalent (create_devlog_entry).

Usage:
    python3 scripts/post_devlog_entry.py --title "..." --body "..." [--author-id 1]
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db_cursor

TITLE_MAX_LENGTH = 200
BODY_MAX_LENGTH = 4000
DEDE_USER_ID = 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Post a devlog entry directly to the DB")
    parser.add_argument("--title", required=True)
    parser.add_argument("--body", required=True)
    parser.add_argument("--author-id", type=int, default=DEDE_USER_ID)
    args = parser.parse_args()

    title = args.title.strip()
    body = args.body.strip()
    if not title or len(title) > TITLE_MAX_LENGTH:
        print(f"Title must be 1-{TITLE_MAX_LENGTH} chars.", file=sys.stderr)
        return 1
    if not body or len(body) > BODY_MAX_LENGTH:
        print(f"Body must be 1-{BODY_MAX_LENGTH} chars.", file=sys.stderr)
        return 1

    with get_db_cursor() as db:
        db.execute(
            """
            INSERT INTO devlog_entries (author_id, title, body)
            VALUES (%s, %s, %s)
            RETURNING id, created_at
            """,
            (args.author_id, title, body),
        )
        row = db.fetchone()

    print(f"devlog entry id={row[0]} created_at={row[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
