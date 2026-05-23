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


def _has_database_url() -> bool:
    return bool(
        (os.getenv("DATABASE_PUBLIC_URL") or "").strip()
        or (os.getenv("DATABASE_URL") or "").strip()
    )


def validate_config() -> None:
    missing = []
    if not DISCORD_BOT_TOKEN:
        missing.append("DISCORD_BOT_TOKEN")
    use_web_embeds = (
        (os.getenv("DISCORD_BOT_USE_WEB_EMBEDS") or "").strip().lower()
        in ("1", "true", "yes")
    )
    if use_web_embeds:
        if not BOT_API_BASE_URL:
            missing.append("BOT_API_BASE_URL")
        if not BOT_API_SECRET and not (os.getenv("SECRET_KEY") or "").strip():
            missing.append("BOT_API_SECRET or SECRET_KEY (for web embed API auth)")
    elif _has_database_url():
        pass  # simplest Railway setup: token + Postgres reference only
    else:
        if not BOT_API_BASE_URL:
            missing.append("BOT_API_BASE_URL")
        if not BOT_API_SECRET and not (os.getenv("SECRET_KEY") or "").strip():
            missing.append(
                "DATABASE_URL (reference Postgres) OR BOT_API_BASE_URL + SECRET_KEY"
            )
    if missing:
        print(f"ERROR: Missing required env vars: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)
    if os.getenv("DISCORD_BOT_URL"):
        print(
            "WARN: DISCORD_BOT_URL is not used; remove it. Use DATABASE_URL from Postgres instead.",
            file=sys.stderr,
        )
