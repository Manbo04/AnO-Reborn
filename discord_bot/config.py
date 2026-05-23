import hashlib
import os
import sys

from dotenv import load_dotenv

load_dotenv()


def _resolve_bot_api_secret() -> str:
    explicit = (os.getenv("BOT_API_SECRET") or "").strip()
    if explicit:
        return explicit
    secret_key = (os.getenv("SECRET_KEY") or "").strip()
    if secret_key:
        return hashlib.sha256(f"ano-bot-api-v1:{secret_key}".encode()).hexdigest()
    return ""


DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "").strip()
BOT_API_SECRET = _resolve_bot_api_secret()
BOT_API_BASE_URL = (
    os.getenv("BOT_API_BASE_URL", "https://affairsandorder.com").strip().rstrip("/")
)
GAME_BASE_URL = os.getenv("GAME_BASE_URL", BOT_API_BASE_URL).strip().rstrip("/")


def validate_config() -> None:
    missing = []
    if not DISCORD_BOT_TOKEN:
        missing.append("DISCORD_BOT_TOKEN")
    if not BOT_API_SECRET and not (os.getenv("SECRET_KEY") or "").strip():
        missing.append("BOT_API_SECRET or SECRET_KEY (reference from web service)")
    if not BOT_API_BASE_URL:
        missing.append("BOT_API_BASE_URL")
    if missing:
        print(f"ERROR: Missing required env vars: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)
    if os.getenv("DISCORD_BOT_URL"):
        print(
            "WARN: DISCORD_BOT_URL is not used by Phase 1 bot; remove it and set BOT_API_BASE_URL instead.",
            file=sys.stderr,
        )
