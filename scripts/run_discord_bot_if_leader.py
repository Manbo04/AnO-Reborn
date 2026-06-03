#!/usr/bin/env python3
"""Run the Discord bot when DISCORD_BOT_TOKEN is set (single leader via Redis).

Use as the start command for a dedicated Railway ``discord-bot`` service::

    python scripts/run_discord_bot_if_leader.py

Requires REDIS_URL (same as Celery). Set DISCORD_BOT_TOKEN and either
BOT_API_SECRET or SECRET_KEY (for derived API auth).
"""

from __future__ import annotations

import os
import sys

# Ensure parent directory is in sys.path so discord_bot module can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import urllib.parse

LOCK_KEY = os.getenv("DISCORD_BOT_LEADER_LOCK_KEY", "discord_bot:leader")
LOCK_TTL = int(os.getenv("DISCORD_BOT_LEADER_LOCK_TTL", "120"))


def main() -> None:
    token = (os.getenv("DISCORD_BOT_TOKEN") or "").strip()
    if not token:
        print("DISCORD_BOT_TOKEN not set; exiting with error so Railway surfaces misconfiguration.")
        sys.exit(1)

    skip_lock = (os.getenv("DISCORD_BOT_SKIP_LEADER_LOCK") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    service = (os.getenv("RAILWAY_SERVICE_NAME") or "").strip().lower()
    if skip_lock or service == "bot":
        print(
            "Skipping Redis leader lock (DISCORD_BOT_SKIP_LEADER_LOCK or RAILWAY_SERVICE_NAME=bot)."
        )
        from discord_bot.main import main as run_bot

        run_bot()
        return

    redis_url = os.getenv("REDIS_URL") or os.getenv("REDIS_PUBLIC_URL")
    if not redis_url:
        print("No REDIS_URL; running bot without leader lock (single instance assumed).")
        from discord_bot.main import main as run_bot

        run_bot()
        return

    try:
        import redis
    except ImportError:
        print("redis package required for leader election")
        sys.exit(2)

    parsed = urllib.parse.urlparse(redis_url)
    client = redis.Redis(
        host=parsed.hostname,
        port=parsed.port or 6379,
        password=parsed.password,
    )

    deadline = time.time() + LOCK_TTL * 2
    acquired = False
    while time.time() < deadline:
        if client.set(LOCK_KEY, os.getpid(), nx=True, ex=LOCK_TTL):
            acquired = True
            break
        time.sleep(5)

    if not acquired:
        print(
            "Leader lock held elsewhere; retrying every 15s "
            f"(key={LOCK_KEY}). Service stays up until acquired."
        )
        while not acquired:
            time.sleep(15)
            if client.set(LOCK_KEY, os.getpid(), nx=True, ex=LOCK_TTL):
                acquired = True
                break
            try:
                client.expire(LOCK_KEY, LOCK_TTL)
            except Exception:
                pass

    print("Discord bot leader lock acquired; starting bot.")
    try:
        while True:
            client.expire(LOCK_KEY, LOCK_TTL)
            from discord_bot.main import main as run_bot

            run_bot()
            break
    finally:
        try:
            client.delete(LOCK_KEY)
        except Exception:
            pass


if __name__ == "__main__":
    main()
