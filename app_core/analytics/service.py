"""First-party player analytics: visits, signup attribution, daily activity.

Everything here is best-effort: a failure is logged and swallowed so analytics can
never break a page view, a login or a signup.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
from datetime import date
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_BOT_RE = re.compile(
    r"bot|crawl|spider|slurp|preview|facebookexternalhit|discordbot|curl|wget|"
    r"python-requests|httpx|headless|monitor|uptime",
    re.I,
)
_OWN_HOSTS = ("affairsandorder.org", "affairsandorder.com", "railway.app")
_SKIP_PREFIXES = (
    "/static", "/api", "/_admin", "/admin", "/health", "/ready", "/deploy-info",
    "/socket.io", "/favicon", "/login/google/callback", "/login/discord/callback",
)
HEARD_FROM_OPTIONS = {
    "google": "Google search",
    "discord": "Discord",
    "reddit": "Reddit",
    "youtube": "YouTube",
    "friend": "A friend invited me",
    "other_game": "Another game or forum",
    "other": "Other",
}


def classify_device(user_agent: str) -> str:
    ua = user_agent or ""
    if re.search(r"iPad|Tablet", ua) or ("Android" in ua and "Mobile" not in ua):
        return "tablet"
    if re.search(r"Mobi|iPhone|Android", ua):
        return "mobile"
    return "desktop"


def is_bot(user_agent: str) -> bool:
    return not user_agent or bool(_BOT_RE.search(user_agent))


def external_referrer_host(referrer: str | None) -> str | None:
    if not referrer:
        return None
    try:
        host = (urlparse(referrer).hostname or "").lower()
    except ValueError:
        return None
    if not host or "." not in host:
        return None
    if host.startswith("www."):
        host = host[4:]
    if any(host == h or host.endswith("." + h) for h in _OWN_HOSTS):
        return None
    return host


def visitor_hash(secret: str, ip: str, user_agent: str, day: date) -> str:
    msg = f"{day.isoformat()}|{ip}|{user_agent}".encode()
    return hmac.new((secret or "").encode(), msg, hashlib.sha256).hexdigest()[:16]


def should_track_path(path: str) -> bool:
    if not path or path.startswith(_SKIP_PREFIXES):
        return False
    return "." not in path.rstrip("/").rsplit("/", 1)[-1]


def _country(headers) -> str | None:
    cc = (headers.get("CF-IPCountry") or "").upper()
    return cc if re.fullmatch(r"[A-Z]{2}", cc) and cc not in ("XX", "T1") else None


def _utm(args, key: str) -> str | None:
    return (args.get(key) or "")[:100] or None


def capture_first_touch() -> None:
    """Remember where this browser first arrived from, for signup attribution."""
    from flask import request, session
    try:
        if "_ft" in session or request.method != "GET" or not should_track_path(request.path):
            return
        session["_ft"] = {
            "ref": external_referrer_host(request.referrer),
            "land": request.path[:200],
            "us": _utm(request.args, "utm_source"),
            "um": _utm(request.args, "utm_medium"),
            "uc": _utm(request.args, "utm_campaign"),
        }
    except Exception as exc:
        logger.warning("capture_first_touch failed: %s", exc)


def record_visit() -> None:
    from flask import current_app, request, session
    try:
        if request.method != "GET" or not should_track_path(request.path):
            return
        ua = request.headers.get("User-Agent", "")
        if is_bot(ua) or session.get("_real_admin_id"):
            return
        from database import client_ip_from_headers, get_db_cursor
        ip = client_ip_from_headers(request.headers, request.remote_addr) or ""
        vh = visitor_hash(current_app.config.get("SECRET_KEY", ""), ip, ua, date.today())
        with get_db_cursor() as db:
            db.execute(
                """INSERT INTO site_visits (visitor_hash, user_id, path, referrer_host,
                       utm_source, utm_medium, utm_campaign, country, device)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (vh, session.get("user_id"), request.path[:200],
                 external_referrer_host(request.referrer),
                 _utm(request.args, "utm_source"), _utm(request.args, "utm_medium"),
                 _utm(request.args, "utm_campaign"), _country(request.headers),
                 classify_device(ua)),
            )
    except Exception as exc:
        logger.warning("record_visit failed: %s", exc)


def record_active_day(db, user_id: int) -> None:
    """Mark today as an active day for user_id, inside the caller's transaction."""
    try:
        db.execute("SAVEPOINT uad")
        db.execute(
            "INSERT INTO user_active_days (user_id, day) VALUES (%s, CURRENT_DATE) "
            "ON CONFLICT DO NOTHING",
            (user_id,),
        )
        db.execute("RELEASE SAVEPOINT uad")
    except Exception as exc:
        try:
            db.execute("ROLLBACK TO SAVEPOINT uad")
        except Exception:
            pass
        logger.warning("record_active_day failed for %s: %s", user_id, exc)


def attach_signup_attribution(db, user_id: int) -> None:
    """Copy first-touch data onto a brand-new user row (caller's uncommitted transaction)."""
    from flask import request, session
    try:
        ft = session.get("_ft") or {}
        heard = request.form.get("heard_from") or session.pop("_heard_from", None)
        heard = heard if heard in HEARD_FROM_OPTIONS else None
        db.execute("SAVEPOINT signup_attr")
        db.execute(
            """UPDATE users SET signup_referrer_host=%s, signup_landing_path=%s,
                   signup_utm_source=%s, signup_utm_medium=%s, signup_utm_campaign=%s,
                   signup_country=%s, signup_device=%s, signup_heard_from=%s,
                   signup_channel_source='tracked'
               WHERE id=%s""",
            (ft.get("ref"), ft.get("land"), ft.get("us"), ft.get("um"), ft.get("uc"),
             _country(request.headers), classify_device(request.headers.get("User-Agent", "")),
             heard, user_id),
        )
        db.execute("RELEASE SAVEPOINT signup_attr")
    except Exception as exc:
        try:
            db.execute("ROLLBACK TO SAVEPOINT signup_attr")
        except Exception:
            pass
        logger.warning("attach_signup_attribution failed for %s: %s", user_id, exc)
