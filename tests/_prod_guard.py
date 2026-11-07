"""Refuse to run the test suite against a production database.

The suite creates and deletes users, wars and money. On 2026-09 a run pointed at production left eight
epoch_ fixture users behind (removed 2026-11-08). Tests must only ever see a local, CI or test-realm database.
"""
import os
from urllib.parse import urlparse

PRODUCTION_HOST_MARKERS = ("railway.internal", "rlwy.net", "railway.app", "proxy.rlwy")


def production_reason(env=None):
    """Return why this environment looks like production, or None if it looks safe."""
    env = os.environ if env is None else env
    if (env.get("ENVIRONMENT") or "").upper() == "PROD":
        return "ENVIRONMENT=PROD"
    if env.get("RAILWAY_ENVIRONMENT_NAME"):
        return f"RAILWAY_ENVIRONMENT_NAME={env.get('RAILWAY_ENVIRONMENT_NAME')}"
    hosts = []
    url = env.get("DATABASE_URL") or ""
    if url:
        hosts.append(urlparse(url).hostname or "")
    if env.get("PG_HOST"):
        hosts.append(env["PG_HOST"])
    for host in hosts:
        if any(m in host.lower() for m in PRODUCTION_HOST_MARKERS):
            return f"database host {host}"
    return None
