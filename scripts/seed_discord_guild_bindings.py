#!/usr/bin/env python3
"""Seed discord_guild_settings panel channel IDs (run after legacy DB is confirmed).

Example (natural-gratitude Discord, 2026-05-23):
  DATABASE_PUBLIC_URL='...' python3 scripts/seed_discord_guild_bindings.py \\
    --guild-id 708006319658893385 \\
    --admin-role-id YOUR_STAFF_ROLE_ID

Uses diagnose_database_schema first; exits if users table missing.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

from dotenv import load_dotenv

load_dotenv()

# From root AI setup (2026-05-23)
DEFAULT_BINDINGS = {
    "readme": "1507759462147162243",
    "leaderboard": "1507759463745065000",
    "war_feed": "1507759465108078804",
    "inspector": "1507759466333077654",
    "world_status": "1507759467603820694",
    "alerts": "1507759469176684774",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--guild-id", default="708006319658893385")
    parser.add_argument(
        "--admin-role-id",
        default="",
        help="Discord role id allowed to use /guild_* and /admin_*",
    )
    args = parser.parse_args()

    probe = subprocess.run(
        [sys.executable, "scripts/diagnose_database_schema.py"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    if probe.returncode != 0:
        print("Aborting: fix database volume first (see docs/DATABASE_SCHEMA_DECISION.md)")
        return 1

    from database import ensure_schema_compat

    ensure_schema_compat()

    for script in (
        "scripts/apply_discord_bot_migration.py",
        "scripts/apply_discord_guild_panels_migration.py",
    ):
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            script,
        )
        if os.path.isfile(path):
            subprocess.run([sys.executable, path], check=False)

    guild_id = str(args.guild_id)
    from discord_bot.guild_store import bind_panel_channel, ensure_guild_row, set_admin_role

    ensure_guild_row(guild_id)
    for panel, channel_id in DEFAULT_BINDINGS.items():
        bind_panel_channel(guild_id, panel, channel_id)
        print(f"Bound {panel} → {channel_id}")

    if args.admin_role_id.strip():
        set_admin_role(guild_id, args.admin_role_id.strip())
        print(f"Admin role → {args.admin_role_id}")

    print("\nDone. In Discord (as admin) run once: /guild_refresh_panels")
    print("Panels will post on next refresh or that command.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
