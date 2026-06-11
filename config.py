"""
Configuration helper for Railway deployment
Parses DATABASE_URL and REDIS_URL into individual components
"""

import os
from urllib.parse import urlparse


def parse_database_url():
    """
    Parse DATABASE_URL into individual components for legacy code compatibility
    Railway provides DATABASE_URL, but legacy code expects PG_* variables
    """
    database_url = os.getenv("DATABASE_URL")

    if database_url:
        # Parse the URL
        parsed = urlparse(database_url)

        # Set individual environment variables if they don't exist
        if not os.getenv("PG_HOST"):
            os.environ["PG_HOST"] = parsed.hostname or "localhost"
        if not os.getenv("PG_PORT"):
            os.environ["PG_PORT"] = str(parsed.port) if parsed.port else "5432"
        if not os.getenv("PG_USER"):
            os.environ["PG_USER"] = parsed.username or "postgres"
        if not os.getenv("PG_PASSWORD"):
            os.environ["PG_PASSWORD"] = parsed.password or ""
        if not os.getenv("PG_DATABASE"):
            # Remove leading slash from path
            os.environ["PG_DATABASE"] = parsed.path[1:] if parsed.path else "postgres"

    return {
        "host": os.getenv("PG_HOST", "localhost"),
        "port": os.getenv("PG_PORT", "5432"),
        "user": os.getenv("PG_USER", "postgres"),
        "password": os.getenv("PG_PASSWORD", ""),
        "database": os.getenv("PG_DATABASE", "postgres"),
    }


def get_redis_url():
    """
    Get Redis URL for Celery broker
    Railway provides REDIS_URL, fallback to broker_url for local dev
    """
    return (
        os.getenv("REDIS_URL") or os.getenv("broker_url") or "redis://localhost:6379/0"
    )


def get_secret_key():
    """
    Get or generate secret key for Flask
    """
    key = (os.getenv("SECRET_KEY") or "").strip()
    if key:
        return key
    if os.getenv("ENVIRONMENT") == "PROD" or os.getenv("RAILWAY_ENVIRONMENT_NAME"):
        raise RuntimeError("SECRET_KEY must be set in production")
    return os.urandom(24).hex()


def validate_production_secrets() -> None:
    """Fail fast when critical secrets are missing on Railway production."""
    if os.getenv("ENVIRONMENT") != "PROD" and not os.getenv("RAILWAY_ENVIRONMENT_NAME"):
        return
    missing = []
    if not (os.getenv("SECRET_KEY") or "").strip():
        missing.append("SECRET_KEY")
    if not (os.getenv("BOT_API_SECRET") or "").strip():
        missing.append("BOT_API_SECRET")
    if missing:
        raise RuntimeError(f"Missing required production env vars: {', '.join(missing)}")


def warn_optional_integrations() -> None:
    """Log non-fatal warnings for optional production integrations."""
    import logging

    if os.getenv("ENVIRONMENT") != "PROD" and not os.getenv("RAILWAY_ENVIRONMENT_NAME"):
        return
    log = logging.getLogger(__name__)
    if not (os.getenv("GOOGLE_CLIENT_ID") or "").strip() or not (
        os.getenv("GOOGLE_CLIENT_SECRET") or ""
    ).strip():
        log.warning(
            "Google OAuth not configured (GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET). "
            "Google login and signup buttons will be hidden."
        )


# Parse on import to ensure environment variables are set
parse_database_url()
