from flask import request, render_template, session, redirect, flash
from helpers import login_required, error

# NOTE: 'app' is NOT imported at module level to avoid circular imports
import os
from dotenv import load_dotenv
import bcrypt
import requests
from string import ascii_uppercase, ascii_lowercase, digits
from datetime import datetime
from random import SystemRandom
from database import (
    fetchone_first,
    get_request_cursor,
    set_user_password,
)

load_dotenv()

DISCORD_API_BASE = os.environ.get("API_BASE_URL", "https://discord.com/api")

# sendgrid imports are performed lazily inside sendEmail to avoid import-time
# failures in environments where the package is not installed


def generateResetCode():
    length = 64
    code = "".join(
        SystemRandom().choice(ascii_uppercase + digits + ascii_lowercase)
        for _ in range(length)
    )
    return code


def generateUrlFromCode(code):
    environment = os.getenv("ENVIRONMENT", "DEV")

    if environment == "PROD":
        url = "https://affairsandorder.com"
    else:
        url = "http://localhost:5000"

    url += f"/reset_password/{code}"

    return url


def send_discord_password_reset_dm(discord_user_id, reset_url):
    """Send a password reset link to the user via Discord bot DM."""
    bot_token = os.getenv("DISCORD_BOT_TOKEN")
    if not bot_token or not discord_user_id:
        return False

    import logging

    logger = logging.getLogger(__name__)
    headers = {
        "Authorization": f"Bot {bot_token}",
        "Content-Type": "application/json",
    }
    message = (
        "**Affairs & Order — Password reset**\n\n"
        "Use this link to set a new password (single use):\n"
        f"{reset_url}\n\n"
        "If you did not request this, ignore this message."
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
                "Discord DM channel create failed: status=%s body=%s",
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
                "Discord DM send failed: status=%s body=%s",
                msg_resp.status_code,
                msg_resp.text[:200],
            )
            return False
        return True
    except Exception as exc:
        logger.error("Discord password reset DM failed: %s", exc)
        return False


def sendEmail(recipient, code):
    url = generateUrlFromCode(code)
    import logging
    from email_utils import send_email

    logger = logging.getLogger(__name__)

    subject = "Affairs & Order | Password change request"
    html_content = (
        f"<p>Click the link below to change your password:</p>"
        f"<p><a href='{url}'>{url}</a></p>"
        f"<p>If you did not request a password change, ignore this email.</p>"
    )
    text_content = f"Click this URL to change your password: {url}"

    if send_email(recipient, subject, html_content, text_content):
        logger.info(f"Password reset email sent to {recipient}")
        return True
    else:
        logger.error(f"Failed to send password reset email to {recipient}")
        return False


# Route for requesting a password reset. After this, user can reset their password.
def request_password_reset():
    import logging

    logger = logging.getLogger(__name__)
    code = generateResetCode()

    with get_request_cursor() as db:
        try:
            cId = session.get("user_id")
        except KeyError:
            cId = None

        if cId:  # User is logged in
            db.execute("SELECT email FROM users WHERE id=%s", (cId,))
            result = db.fetchone()
            email = result[0] if result else None
        else:
            email = request.form.get("email")
            db.execute("SELECT id FROM users WHERE email=%s", (email,))
            result = db.fetchone()
            if not result:
                # Don't reveal whether an email exists; behave as if request succeeded
                flash(
                    "If an account exists with that email, a reset link has been sent."
                )
                return redirect("/forgot_password")
            cId = result[0]

        # Insert or update reset code record for the user (idempotent)
        db.execute(
            "INSERT INTO reset_codes (url_code, user_id, created_at) "
            "VALUES (%s, %s, %s) "
            "ON CONFLICT (user_id) DO UPDATE SET url_code = EXCLUDED.url_code, "
            "created_at = EXCLUDED.created_at "
            "RETURNING user_id",
            (code, cId, int(datetime.now().timestamp())),
        )
        inserted = db.fetchone()
        client_ip = request.headers.get("X-Forwarded-For") or request.remote_addr
        if inserted and inserted[0] == cId:
            logger.info(
                "request_password_reset: set reset code for user_id=%s ip=%s",
                cId,
                client_ip,
            )
        else:
            logger.warning(
                "request_password_reset: unexpected upsert result for user_id=%s ip=%s",
                cId,
                client_ip,
            )

    reset_url = generateUrlFromCode(code)

    # Logged-in account page: prefer Discord DM or immediate reset link (no email)
    if cId:
        discord_id = None
        with get_request_cursor() as db:
            try:
                db.execute("SELECT discord_id FROM users WHERE id=%s", (cId,))
                row = db.fetchone()
                discord_id = row[0] if row else None
            except Exception:
                db.connection.rollback()

        if discord_id and send_discord_password_reset_dm(discord_id, reset_url):
            flash("A password reset link was sent to your Discord DMs.")
            return redirect("/account")

        if discord_id:
            flash(
                "Could not send a Discord message. "
                "Open the reset page below or link Discord and try again."
            )
        return redirect(f"/reset_password/{code}")

    # Forgot-password page (not logged in): try email, then generic response
    if email:
        try:
            sendEmail(email, code)
        except Exception:
            pass

    flash("If an account exists with that email, a reset link has been sent.")
    return redirect("/forgot_password")


# Route for resetting password after request for changing password has been submitted.
def reset_password(code):
    if request.method == "GET":
        return render_template("reset_password.html", code=code)
    else:
        import logging

        logger = logging.getLogger(__name__)

        # Validate input password
        new_password_raw = request.form.get("password")
        if not new_password_raw:
            flash("Please provide a new password.")
            return render_template("reset_password.html", code=code), 400
        if len(new_password_raw) < 6:
            flash("Password must be at least 6 characters long.")
            return render_template("reset_password.html", code=code), 400

        new_password = new_password_raw.encode("utf-8")

        try:
            with get_request_cursor() as db:
                logger.debug("Received URL code: %s", code)
                import time as _time

                cutoff = str(int(_time.time()) - 86400)
                db.execute(
                    """
                    SELECT user_id FROM reset_codes
                    WHERE url_code=%s AND created_at::bigint > %s
                    """,
                    (code, cutoff),
                )
                user_id = fetchone_first(db)
                if user_id is None:
                    return error(400, "Invalid or expired reset code.")

                hashed = bcrypt.hashpw(new_password, bcrypt.gensalt(14)).decode(
                    "utf-8"
                )
                set_user_password(db, int(user_id), hashed)
                db.execute(
                    "DELETE FROM reset_codes WHERE url_code=%s",
                    (code,),
                )
        except Exception as exc:
            # Send to Sentry if available and return friendly id
            try:
                import sentry_sdk

                # capture_exception supports passing the exception instance
                event_id = sentry_sdk.capture_exception(exc)
            except Exception:
                import logging as _logging

                _logger = _logging.getLogger(__name__)
                event_id = None
                _logger.exception("Error resetting password for code %s", code)

            if event_id:
                return error(
                    500,
                    (
                        "An error occurred while resetting your password. "
                        f"Please report this id: {event_id}"
                    ),
                )
            else:
                return error(
                    500,
                    (
                        "An error occurred while resetting your password. "
                        "Please try again later."
                    ),
                )

        return redirect("/")


@login_required
def change():
    with get_request_cursor() as db:
        cId = session["user_id"]

        password_raw = request.form.get("current_password")
        if not password_raw:
            return error(400, "No password provided")
        password = password_raw.encode("utf-8")

        email = request.form.get("email")
        name = request.form.get("name")

        db.execute("SELECT hash FROM users WHERE id=%s", (cId,))
        row = db.fetchone()
        if not row or not row[0]:
            return error(500, "Account data is missing. Please contact support.")
        hash_value = row[0].encode("utf-8")

        if bcrypt.checkpw(password, hash_value):
            if email:
                db.execute("UPDATE users SET email=%s WHERE id=%s", (email, cId))
            if name:
                db.execute("UPDATE users SET username=%s WHERE id=%s", (name, cId))
        else:
            return error(401, "Incorrect password")

    return redirect("/account")


@login_required
def generate_discord_link_code():
    import logging

    logger = logging.getLogger(__name__)
    from bot_api import create_discord_link_code
    from database import discord_link_codes_table_exists

    if not discord_link_codes_table_exists():
        flash(
            "Discord bot linking is not available yet (database migration pending)."
        )
        return redirect("/account")

    with get_request_cursor() as db:
        cId = session["user_id"]
        password_raw = request.form.get("password")
        if not password_raw:
            flash("You must provide your password to generate a Discord link code.")
            return redirect("/account")

        db.execute("SELECT hash FROM users WHERE id=%s", (cId,))
        row = db.fetchone()
        if not row or not row[0]:
            return error(500, "Account data is missing.")

        if not bcrypt.checkpw(password_raw.encode("utf-8"), row[0].encode("utf-8")):
            flash("Incorrect password.")
            return redirect("/account")

    try:
        create_discord_link_code(cId)
    except Exception as exc:
        logger.warning("generate_discord_link_code failed: %s", exc)
        flash("Could not generate link code. Please try again later.")
        return redirect("/account")

    flash(
        "Discord bot link code generated — copy it from the box below before it expires."
    )
    logger.info("Generated Discord link code for user_id=%s", cId)
    return redirect("/account")


@login_required
def generate_recovery_key():
    import secrets
    import logging
    logger = logging.getLogger(__name__)
    
    with get_request_cursor() as db:
        cId = session["user_id"]
        
        # Check current password before generating
        password_raw = request.form.get("password")
        if not password_raw:
            flash("You must provide your password to generate a recovery key.")
            return redirect("/account")
        
        db.execute("SELECT hash FROM users WHERE id=%s", (cId,))
        row = db.fetchone()
        if not row or not row[0]:
            return error(500, "Account data is missing.")
            
        if not bcrypt.checkpw(password_raw.encode("utf-8"), row[0].encode("utf-8")):
            flash("Incorrect password.")
            return redirect("/account")
            
        raw_key = secrets.token_hex(8)
        hashed_key = bcrypt.hashpw(raw_key.encode("utf-8"), bcrypt.gensalt(14)).decode("utf-8")
        
        db.execute("UPDATE users SET recovery_key=%s WHERE id=%s", (hashed_key, cId))
        
        flash(f"Your new Backup Recovery Key is: {raw_key} - SAVE THIS SECURELY. IT WILL ONLY BE SHOWN ONCE.")
        logger.info("Generated new recovery key for user_id=%s", cId)
        
    return redirect("/account")


def reset_password_recovery_key():
    import logging
    logging.getLogger(__name__)

    if request.method == "POST":
        username = request.form.get("username")
        recovery_key = request.form.get("recovery_key")

        if not username or not recovery_key:
            flash("Username and Recovery Key are required.")
            return redirect("/forgot_password")

        with get_request_cursor() as db:
            db.execute("SELECT id, recovery_key FROM users WHERE username=%s LIMIT 1", (username,))
            user = db.fetchone()

            if not user or not user[1]:
                flash("Invalid username or recovery key.")
                return redirect("/forgot_password")

            user_id = user[0]
            stored_val = user[1]
            
            if not stored_val:
                flash("Invalid username or recovery key.")
                return redirect("/forgot_password")
                
            stored_hash = stored_val.encode("utf-8")

            if bcrypt.checkpw(recovery_key.encode("utf-8"), stored_hash):
                session['reset_user_id'] = user_id
                # Wipe the recovery key so it can only be used once
                db.execute("UPDATE users SET recovery_key=NULL WHERE id=%s", (user_id,))
                return redirect("/discord_reset_password_page")
            else:
                flash("Invalid username or recovery key.")
                return redirect("/forgot_password")
    
    return redirect("/forgot_password")


def discord_reset_password_page():
    if 'reset_user_id' not in session:
        return error(400, "Reset session expired or invalid.")

    if request.method == "GET":
        return render_template("reset_password_discord.html")
    else:
        import logging
        logger = logging.getLogger(__name__)

        new_password_raw = request.form.get("password")
        if not new_password_raw:
            flash("Please provide a new password.")
            return render_template("reset_password_discord.html"), 400
        if len(new_password_raw) < 6:
            flash("Password must be at least 6 characters long.")
            return render_template("reset_password_discord.html"), 400

        new_password = new_password_raw.encode("utf-8")
        user_id = session.pop('reset_user_id')

        try:
            with get_request_cursor() as db:
                hashed = bcrypt.hashpw(new_password, bcrypt.gensalt(14)).decode(
                    "utf-8"
                )
                set_user_password(db, int(user_id), hashed)
                logger.info(
                    "Password reset successful via Discord for user_id=%s",
                    user_id,
                )
        except Exception as exc:
            logger.exception(
                "discord_reset_password_page failed for user_id=%s: %s",
                user_id,
                exc,
            )
            return error(
                500,
                "An error occurred while resetting your password. Please try again later.",
            )

        flash("Password successfully reset. You can now log in.")
        return redirect("/")


def register_change_routes(app_instance):
    """Register all change routes with the Flask app instance"""
    app_instance.add_url_rule(
        "/request_password_reset",
        "request_password_reset",
        request_password_reset,
        methods=["POST"],
    )
    app_instance.add_url_rule(
        "/reset_password/<code>",
        "reset_password",
        reset_password,
        methods=["GET", "POST"],
    )
    app_instance.add_url_rule("/change", "change", change, methods=["POST"])
    app_instance.add_url_rule(
        "/discord_reset_password_page",
        "discord_reset_password_page",
        discord_reset_password_page,
        methods=["GET", "POST"],
    )
    app_instance.add_url_rule(
        "/generate_recovery_key",
        "generate_recovery_key",
        generate_recovery_key,
        methods=["POST"],
    )
    app_instance.add_url_rule(
        "/generate_discord_link_code",
        "generate_discord_link_code",
        generate_discord_link_code,
        methods=["POST"],
    )
    app_instance.add_url_rule(
        "/reset_password_recovery_key",
        "reset_password_recovery_key",
        reset_password_recovery_key,
        methods=["POST"],
    )
