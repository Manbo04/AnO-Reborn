"""
Configuration helper for Railway deployment
Parses DATABASE_URL and REDIS_URL into individual components
"""

import os
from urllib.parse import urlparse


def parse_database_url() -> dict[str, str]:
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


def get_redis_url() -> str:
    """
    Get Redis URL for Celery broker
    Railway provides REDIS_URL, fallback to broker_url for local dev
    """
    return (
        os.getenv("REDIS_URL") or os.getenv("broker_url") or "redis://localhost:6379/0"
    )


def get_secret_key() -> str:
    """
    Get or generate secret key for Flask
    """
    return os.getenv("SECRET_KEY") or os.urandom(24).hex()


# Parse on import to ensure environment variables are set
parse_database_url()
