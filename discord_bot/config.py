import os
import sys

from dotenv import load_dotenv

load_dotenv()

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "").strip()
BOT_API_SECRET = os.getenv("BOT_API_SECRET", "").strip()
BOT_API_BASE_URL = (
    os.getenv("BOT_API_BASE_URL", "https://affairsandorder.com").strip().rstrip("/")
)
GAME_BASE_URL = os.getenv("GAME_BASE_URL", BOT_API_BASE_URL).strip().rstrip("/")


def validate_config() -> None:
    missing = []
    if not DISCORD_BOT_TOKEN:
        missing.append("DISCORD_BOT_TOKEN")
    if not BOT_API_SECRET:
        missing.append("BOT_API_SECRET")
    if not BOT_API_BASE_URL:
        missing.append("BOT_API_BASE_URL")
    if missing:
        print(f"ERROR: Missing required env vars: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)
