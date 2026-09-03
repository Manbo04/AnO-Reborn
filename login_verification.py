"""New-location login verification.

Following the Discord-login account-takeover incident (2026-09-03, silent
email-based account merge -- fixed separately in signup.py's callback()),
logging in from an IP never seen before for that account no longer completes
immediately. Instead a single-use confirmation link is sent to the account's
linked Discord DM (preferred) or verified email, and the session is only
established once that link is opened. This closes the gap where a stolen
password, a guessed recovery flow, or any future auth bug still can't be
used from an unrecognized location without the real owner's Discord/email.

Accounts with no reachable Discord or verified email are exempted (fail
open with a warning log) rather than risk permanently locking someone out --
plenty of legacy/test accounts in this DB have neither.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from string import ascii_lowercase, ascii_uppercase, digits
from random import SystemRandom

import requests
from flask import flash, redirect, session

from database import get_db_cursor, get_request_cursor, log_login_event

logger = logging.getLogger(__name__)

DISCORD_API_BASE = os.environ.get("API_BASE_URL", "https://discord.com/api")
TOKEN_TTL = timedelta(minutes=20)


def _generate_token() -> str:
    return "".join(
        SystemRandom().choice(ascii_uppercase + ascii_lowercase + digits)
        for _ in range(48)
    )


def _base_url() -> str:
    environment = os.getenv("ENVIRONMENT", "DEV")
    if environment == "PROD" or os.getenv("RAILWAY_ENVIRONMENT_NAME"):
        return "https://affairsandorder.org"
    return "http://localhost:5000"


def ip_is_known_for_user(user_id: int, ip: str | None) -> bool:
    """True if this IP has logged into this account before, or the account
    has no login history yet (first-ever login is trusted as the baseline)."""
    if not ip:
        return True
    try:
        with get_request_cursor() as db:
            db.execute(
                "SELECT 1 FROM login_events WHERE user_id=%s LIMIT 1", (user_id,)
            )
            if db.fetchone() is None:
                return True
            db.execute(
                "SELECT 1 FROM login_events WHERE user_id=%s AND ip=%s LIMIT 1",
                (user_id, ip),
            )
            return db.fetchone() is not None
    except Exception:
        # Fail open on lookup errors -- an outage here must never lock
        # everyone out of the whole site.
        logger.exception("ip_is_known_for_user check failed for user_id=%s", user_id)
        return True


def _send_discord_dm(discord_user_id: str, confirm_url: str) -> bool:
    bot_token = os.getenv("DISCORD_BOT_TOKEN")
    if not bot_token or not discord_user_id:
        return False
    headers = {"Authorization": f"Bot {bot_token}", "Content-Type": "application/json"}
    message = (
        "**Affairs & Order — New login location**\n\n"
        "Someone just tried to log into your nation from a location we haven't "
        "seen before. If this was you, confirm it here (single use, expires in "
        f"20 minutes):\n{confirm_url}\n\n"
        "If this wasn't you, ignore this message and consider changing your "
        "password."
    )
    try:
        channel_resp = requests.post(
            f"{DISCORD_API_BASE}/users/@me/channels",
            headers=headers,
            json={"recipient_id": str(discord_user_id)},
            timeout=10,
        )
        if not channel_resp.ok:
            logger.warning(
                "login verification DM channel create failed: status=%s body=%s",
                channel_resp.status_code,
                channel_resp.text[:200],
            )
            return False
        channel_id = channel_resp.json().get("id")
        if not channel_id:
            return False
        msg_resp = requests.post(
            f"{DISCORD_API_BASE}/channels/{channel_id}/messages",
            headers=headers,
            json={"content": message},
            timeout=10,
        )
        if not msg_resp.ok:
            logger.warning(
                "login verification DM send failed: status=%s body=%s",
                msg_resp.status_code,
                msg_resp.text[:200],
            )
            return False
        return True
    except Exception:
        logger.exception("login verification DM failed")
        return False


def _send_email(email: str, confirm_url: str) -> bool:
    try:
        from email_utils import send_email, is_email_configured

        if not is_email_configured():
            return False
        subject = "Affairs & Order | New login location"
        html_content = (
            "<p>Someone just tried to log into your nation from a location we "
            "haven't seen before. If this was you, click below to confirm "
            "(single use, expires in 20 minutes):</p>"
            f"<p><a href='{confirm_url}'>{confirm_url}</a></p>"
            "<p>If this wasn't you, ignore this email and consider changing "
            "your password.</p>"
        )
        text_content = f"Confirm this login: {confirm_url}"
        return send_email(email, subject, html_content, text_content)
    except Exception:
        logger.exception("login verification email failed")
        return False


def start_login_verification(
    user_id: int, ip: str | None, fingerprint: str | None, auth_type: str
) -> bool:
    """Create a pending verification and try to deliver it. Returns True if a
    confirmation link was actually sent (Discord DM or email), False if there
    was no reachable channel -- callers should fail the login open in that
    case rather than lock the account holder out."""
    with get_db_cursor() as db:
        db.execute(
            "SELECT email, discord_id, is_verified FROM users WHERE id=%s",
            (user_id,),
        )
        row = db.fetchone()
    if not row:
        return False
    email, discord_id, is_verified = row[0], row[1], row[2]

    token = _generate_token()
    expires_at = datetime.now(timezone.utc) + TOKEN_TTL
    confirm_url = f"{_base_url()}/confirm_login/{token}"

    delivered = False
    delivery_method = None
    if discord_id and _send_discord_dm(discord_id, confirm_url):
        delivered = True
        delivery_method = "discord"
    elif email and is_verified and _send_email(email, confirm_url):
        delivered = True
        delivery_method = "email"

    if not delivered:
        logger.warning(
            "login verification: no reachable Discord/email for user_id=%s "
            "(discord_id=%s, is_verified=%s) -- allowing login through unverified",
            user_id,
            bool(discord_id),
            is_verified,
        )
        return False

    with get_db_cursor() as db:
        db.execute(
            """
            INSERT INTO login_verifications
                (user_id, token, ip, fingerprint, auth_type, delivery_method, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (user_id, token, ip, fingerprint, auth_type, delivery_method, expires_at),
        )
    return True


def flash_pending_verification_and_redirect():
    flash(
        "New location detected. We sent a confirmation link to your Discord "
        "DMs or email -- open it to finish logging in."
    )
    return redirect("/login")


def complete_or_verify_login(user_id: int, ip: str | None, fingerprint: str | None, auth_type: str):
    """Call this instead of directly setting session['user_id'] after any
    credential check succeeds. Either completes the login immediately (known
    IP, or no reachable verification channel) or sends a confirmation link
    and redirects back to /login with a flash message.

    Returns a Flask response -- callers should `return` it directly.
    """
    if ip_is_known_for_user(user_id, ip):
        session.clear()
        session["user_id"] = user_id
        session.permanent = True
        session.modified = True
        try:
            log_login_event(user_id, ip, fingerprint, auth_type)
        except Exception:
            pass
        return redirect("/")

    if start_login_verification(user_id, ip, fingerprint, auth_type):
        return flash_pending_verification_and_redirect()

    # No reachable Discord/email -- don't lock the real owner out.
    session.clear()
    session["user_id"] = user_id
    session.permanent = True
    session.modified = True
    try:
        log_login_event(user_id, ip, fingerprint, f"{auth_type}_unverified_location")
    except Exception:
        pass
    return redirect("/")


def confirm_login(token: str):
    """Route handler for GET /confirm_login/<token>."""
    from flask import current_app
    import datetime as dt_module

    with get_db_cursor() as db:
        db.execute(
            """
            SELECT id, user_id, ip, fingerprint, auth_type, expires_at, consumed_at
            FROM login_verifications WHERE token=%s
            """,
            (token,),
        )
        row = db.fetchone()

    if not row:
        flash("This login confirmation link is invalid.")
        return redirect("/login")

    v_id, user_id, ip, fingerprint, auth_type, expires_at, consumed_at = row

    if consumed_at is not None:
        flash("This login confirmation link was already used.")
        return redirect("/login")

    now = dt_module.datetime.now(dt_module.timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=dt_module.timezone.utc)
    if expires_at < now:
        flash("This login confirmation link has expired. Please log in again.")
        return redirect("/login")

    with get_db_cursor() as db:
        db.execute(
            "UPDATE login_verifications SET consumed_at=NOW() WHERE id=%s", (v_id,)
        )

    current_app.config["SESSION_PERMANENT"] = True
    import datetime as dt2
    current_app.permanent_session_lifetime = dt2.timedelta(days=365)

    session.clear()
    session["user_id"] = user_id
    session.permanent = True
    session.modified = True
    try:
        log_login_event(user_id, ip, fingerprint, auth_type)
    except Exception:
        pass

    flash("Login confirmed.")
    return redirect("/")


def register_login_verification_routes(app_instance):
    app_instance.add_url_rule(
        "/confirm_login/<token>", "confirm_login", confirm_login, methods=["GET"]
    )
