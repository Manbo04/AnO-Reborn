"""New-location login alerts.

Following the Discord-login account-takeover incident (2026-09-03, silent
email-based account merge -- fixed separately in signup.py's callback()),
a login from an IP never seen before for that account triggers a heads-up
(not a block): a single-use "secure your account" link goes to the
account's linked Discord DM (preferred) or verified email. The login
itself always completes immediately either way -- gating it behind a
Discord/email click generated real "why can't I log in" confusion for
legitimate players switching wifi/phones/laptops, not just attackers.
Clicking the link never signs anyone in; it only lets the real owner kick
off a password reset delivered to their own Discord/email if it wasn't
them.
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
        "Your nation was just logged into from a location we haven't seen "
        "before. If this was you, no action needed. If it wasn't, secure "
        f"your account here:\n{confirm_url}\n"
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
            "<p>Your nation was just logged into from a location we haven't "
            "seen before. If this was you, no action needed. If it wasn't, "
            "secure your account here:</p>"
            f"<p><a href='{confirm_url}'>{confirm_url}</a></p>"
        )
        text_content = f"If this wasn't you, secure your account: {confirm_url}"
        return send_email(email, subject, html_content, text_content)
    except Exception:
        logger.exception("login verification email failed")
        return False


def start_login_verification(
    user_id: int, ip: str | None, fingerprint: str | None, auth_type: str
) -> bool:
    """Create a pending "secure your account" link and try to deliver it as a
    new-location alert. Always records a login_verifications row -- whether
    or not delivery actually succeeds -- so a failed/silent alert still
    leaves a durable, auditable trace that a new-location login happened
    (see the 2026-09-05 incident: delivery had silently failed with zero
    record, so nobody could tell the alert had ever fired). Returns True if
    it was actually sent (Discord DM or email), False if there was no
    reachable channel -- either way the login this is about has already
    completed and the row is written regardless."""
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
            "(discord_id=%s, is_verified=%s) -- allowing login through "
            "unverified, recording undelivered attempt",
            user_id,
            bool(discord_id),
            is_verified,
        )

    with get_db_cursor() as db:
        db.execute(
            """
            INSERT INTO login_verifications
                (user_id, token, ip, fingerprint, auth_type, delivery_method, delivered, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (user_id, token, ip, fingerprint, auth_type, delivery_method, delivered, expires_at),
        )
    return delivered


def complete_or_verify_login(user_id: int, ip: str | None, fingerprint: str | None, auth_type: str):
    """Call this instead of directly setting session['user_id'] after any
    credential check succeeds.

    The login always completes immediately -- this does not block or add
    friction to normal play (players switch wifi/phones/laptops constantly,
    and gating every new IP behind a Discord/email click generated real
    "why can't I log in" confusion for legitimate players, not just
    attackers). When the IP is one we haven't seen before for this account,
    a best-effort heads-up (not a confirmation requirement) still goes to
    the account's linked Discord DM or verified email, so the real owner at
    least finds out promptly if it wasn't them.

    Returns a Flask response -- callers should `return` it directly.
    """
    session.clear()
    session["user_id"] = user_id
    session.permanent = True
    session.modified = True
    try:
        log_login_event(user_id, ip, fingerprint, auth_type)
    except Exception:
        pass

    if not ip_is_known_for_user(user_id, ip):
        try:
            start_login_verification(user_id, ip, fingerprint, auth_type)
        except Exception:
            logger.exception("new-location alert failed for user_id=%s", user_id)

    return redirect("/")


def confirm_login(token: str):
    """Route handler for GET /confirm_login/<token>.

    This link is a "secure my account" action, NOT a login grant -- the
    login it's about already completed (see complete_or_verify_login).
    Clicking it never signs the clicker in as anyone; it just lets the real
    account owner kick off a normal password reset (delivered to their own
    linked Discord/email, same as /request_password_reset) if the new-
    location login wasn't them.
    """
    import datetime as dt_module

    with get_db_cursor() as db:
        db.execute(
            "SELECT id, user_id, expires_at, consumed_at FROM login_verifications WHERE token=%s",
            (token,),
        )
        row = db.fetchone()

    if not row:
        flash("This link is invalid.")
        return redirect("/login")

    v_id, user_id, expires_at, consumed_at = row

    if consumed_at is not None:
        flash("This link was already used.")
        return redirect("/login")

    now = dt_module.datetime.now(dt_module.timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=dt_module.timezone.utc)
    if expires_at < now:
        flash("This link has expired.")
        return redirect("/login")

    with get_db_cursor() as db:
        db.execute(
            "UPDATE login_verifications SET consumed_at=NOW() WHERE id=%s", (v_id,)
        )

    from change import generateResetCode, generateUrlFromCode, send_discord_password_reset_dm

    code = generateResetCode()
    with get_db_cursor() as db:
        db.execute(
            """
            INSERT INTO reset_codes (url_code, user_id, created_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET url_code = EXCLUDED.url_code,
            created_at = EXCLUDED.created_at
            """,
            (code, user_id, int(dt_module.datetime.now(dt_module.timezone.utc).timestamp())),
        )
        db.execute("SELECT email, discord_id FROM users WHERE id=%s", (user_id,))
        urow = db.fetchone()

    reset_url = generateUrlFromCode(code)
    sent = False
    if urow:
        email, discord_id = urow[0], urow[1]
        if discord_id:
            sent = send_discord_password_reset_dm(discord_id, reset_url)
        if not sent and email:
            from change import sendEmail

            sent = sendEmail(email, code)

    if sent:
        flash("Confirmed -- a password reset link was sent to secure your account.")
    else:
        flash("Confirmed. Please use /forgot_password to secure your account.")
    return redirect("/login")


def register_login_verification_routes(app_instance):
    app_instance.add_url_rule(
        "/confirm_login/<token>", "confirm_login", confirm_login, methods=["GET"]
    )
