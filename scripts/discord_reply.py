#!/usr/bin/env python3
"""Post a reply to a Discord channel/thread as the game bot, with an @mention.

Used by the automated hourly agent to tell a player their bug was fixed.

Usage:
    python3 scripts/discord_reply.py <channel_id> <user_id> "message text"

The user is @mentioned at the start. The bot token is pulled from Railway
(the logged-in railway CLI), so nothing is hardcoded.
"""
import json
import subprocess
import sys
import urllib.request


def token() -> str | None:
    try:
        r = subprocess.run(
            ["railway", "variables", "--service", "bot", "--json"],
            capture_output=True, text=True, timeout=60,
        )
        if r.returncode == 0 and r.stdout.strip():
            return json.loads(r.stdout).get("DISCORD_BOT_TOKEN")
    except Exception:
        pass
    return None


def main() -> int:
    if len(sys.argv) < 4:
        print("usage: discord_reply.py <channel_id> <user_id> <message>")
        return 2
    channel_id, user_id, message = sys.argv[1], sys.argv[2], sys.argv[3]
    tok = token()
    if not tok:
        print("ERROR: no Discord bot token available")
        return 1
    content = f"<@{user_id}> {message}"[:1990]
    req = urllib.request.Request(
        f"https://discord.com/api/v10/channels/{channel_id}/messages",
        data=json.dumps(
            {"content": content, "allowed_mentions": {"parse": ["users"]}}
        ).encode(),
        headers={
            "Authorization": f"Bot {tok}",
            "Content-Type": "application/json",
            "User-Agent": "ano-agent/1.0",
        },
    )
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=20).read())
        print("sent message id:", resp.get("id"))
        return 0
    except Exception as e:
        print("ERROR posting:", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
