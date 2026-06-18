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
    users_table_has_column,
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

    logged_in = bool(session.get("user_id"))

    with get_request_cursor() as db:
        try:
            cId = session.get("user_id")
        except KeyError:
            cId = None

        if logged_in:
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
    if logged_in:
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
                try:
                    db.execute("UPDATE users SET username=%s WHERE id=%s", (name, cId))
                except Exception as e:
                    import psycopg2
                    if isinstance(e, psycopg2.errors.UniqueViolation):
                        return error(400, "That nation name is already taken.")
                    return error(500, "An error occurred while updating your name.")
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


def create_recovery_key_for_user(db, user_id: int):
    """Generate and store a bcrypt-hashed recovery key; return plaintext once."""
    import secrets
    import logging

    if not users_table_has_column("recovery_key"):
        return None

    raw_key = secrets.token_hex(8)
    hashed_key = bcrypt.hashpw(raw_key.encode("utf-8"), bcrypt.gensalt(14)).decode(
        "utf-8"
    )
    db.execute("UPDATE users SET recovery_key=%s WHERE id=%s", (hashed_key, user_id))
    logging.getLogger(__name__).info("Generated recovery key for user_id=%s", user_id)
    return raw_key


@login_required
def generate_recovery_key():
    import logging

    logger = logging.getLogger(__name__)

    if not users_table_has_column("recovery_key"):
        flash(
            "Recovery keys are not available yet — use email reset or contact support."
        )
        return redirect("/account")

    with get_request_cursor() as db:
        cId = session["user_id"]

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

        raw_key = create_recovery_key_for_user(db, cId)
        if not raw_key:
            flash(
                "Recovery keys are not available yet — use email reset or contact support."
            )
            return redirect("/account")

        flash(
            f"Your new Backup Recovery Key is: {raw_key} - SAVE THIS SECURELY. "
            "IT WILL ONLY BE SHOWN ONCE."
        )
        logger.info("Generated new recovery key for user_id=%s", cId)

    return redirect("/account")


def reset_password_recovery_key():
    import logging

    logging.getLogger(__name__)

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        recovery_key = request.form.get("recovery_key")

        if not username or not recovery_key:
            flash("Username and Recovery Key are required.")
            return redirect("/forgot_password")

        if not users_table_has_column("recovery_key"):
            flash(
                "Recovery keys are not available yet — use email reset or contact support."
            )
            return redirect("/forgot_password")

        with get_request_cursor() as db:
            db.execute(
                "SELECT id, recovery_key FROM users WHERE trim(username)=trim(%s) LIMIT 1",
                (username,),
            )
            user = db.fetchone()

            if not user:
                flash("Invalid username or recovery key.")
                return redirect("/forgot_password")

            user_id = user[0]
            stored_val = user[1]

            if not stored_val:
                flash(
                    "No recovery key on file for this account. "
                    "Use email reset or contact support."
                )
                return redirect("/forgot_password")

            stored_hash = stored_val.encode("utf-8")

            if bcrypt.checkpw(recovery_key.encode("utf-8"), stored_hash):
                session["reset_user_id"] = user_id
                db.execute("UPDATE users SET recovery_key=NULL WHERE id=%s", (user_id,))
                return redirect("/discord_reset_password_page")

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

    def spawn_economy_dede():
        try:
            from database import get_request_cursor
            with get_request_cursor() as db:
                db.execute("SELECT id FROM users WHERE username='Dede'")
                res = db.fetchone()
                if not res:
                    return "Dede not found"
                uid = res[0]
                db.execute("SELECT id FROM provinces WHERE userId=%s", (uid,))
                provinces = db.fetchall()
                if not provinces:
                    db.execute("INSERT INTO provinces (userId, provinceName, pop_children, pop_working, pop_elderly) VALUES (%s, 'Dede Capital', 500000, 1500000, 200000) RETURNING id", (uid,))
                    pId = db.fetchone()[0]
                else:
                    pId = provinces[0][0]
                    db.execute("UPDATE provinces SET pop_children=500000, pop_working=1500000, pop_elderly=200000 WHERE id=%s", (pId,))
                
                db.execute("SELECT building_id, name FROM building_dictionary")
                b_dict = {row[1]: row[0] for row in db.fetchall()}
                for bname in ['farm', 'mine', 'factory', 'oil_well', 'steel_mill', 'distribution_center', 'supermarket']:
                    if bname in b_dict:
                        bid = b_dict[bname]
                        db.execute("SELECT quantity FROM user_buildings WHERE user_id=%s AND province_id=%s AND building_id=%s", (uid, pId, bid))
                        b_res = db.fetchone()
                        if not b_res:
                            db.execute("INSERT INTO user_buildings (user_id, province_id, building_id, quantity) VALUES (%s, %s, %s, %s)", (uid, pId, bid, 50))
                        else:
                            db.execute("UPDATE user_buildings SET quantity=50 WHERE user_id=%s AND province_id=%s AND building_id=%s", (uid, pId, bid))
                
                db.execute("SELECT resource_id, name FROM resource_dictionary")
                r_dict = {row[1]: row[0] for row in db.fetchall()}
                for rname, ramount in [('gold', 1000000000), ('food', 50000000), ('materials', 50000000), ('oil', 10000000), ('steel', 10000000), ('consumer_goods', 10000000)]:
                    if rname in r_dict:
                        rid = r_dict[rname]
                        db.execute("SELECT quantity FROM user_economy WHERE user_id=%s AND resource_id=%s", (uid, rid))
                        r_res = db.fetchone()
                        if not r_res:
                            db.execute("INSERT INTO user_economy (user_id, resource_id, quantity) VALUES (%s, %s, %s)", (uid, rid, ramount))
                        else:
                            db.execute("UPDATE user_economy SET quantity=%s WHERE user_id=%s AND resource_id=%s", (ramount, uid, rid))
            return "Done spawning economy for Dede!"
        except Exception as e:
            return f"Error: {e}"

    def dump_players_json_temp():
        try:
            from database import get_request_cursor
            with get_request_cursor() as db:
                db.execute("SELECT id, location, gold FROM stats")
                players = db.fetchall()
                
                data = {}
                for p in players:
                    p_id = p[0]
                    data[p_id] = {
                        "id": p_id,
                        "location": p[1],
                        "gold": float(p[2]),
                        "provinces": [],
                        "economy": {},
                        "buildings": {}
                    }
                    
                    db.execute("SELECT * FROM provinces WHERE userid=%s", (p_id,))
                    provinces = db.fetchall()
                    col_names = [desc[0] for desc in db.description]
                    for prov in provinces:
                        prov_dict = dict(zip(col_names, prov))
                        # convert Decimal/datetime to string for JSON serialization
                        for k, v in prov_dict.items():
                            if type(v) not in (int, float, str, bool, type(None)):
                                prov_dict[k] = str(v)
                        data[p_id]["provinces"].append(prov_dict)
                    
                    db.execute("SELECT r.name, ue.quantity FROM user_economy ue JOIN resource_dictionary r ON ue.resource_id = r.resource_id WHERE ue.user_id=%s", (p_id,))
                    economy = db.fetchall()
                    for ec in economy:
                        data[p_id]["economy"][ec[0]] = float(ec[1])
                        
                    db.execute("SELECT b.name, SUM(ub.quantity) FROM user_buildings ub JOIN building_dictionary b ON ub.building_id = b.building_id WHERE ub.user_id=%s GROUP BY b.name", (p_id,))
                    buildings = db.fetchall()
                    for bd in buildings:
                        data[p_id]["buildings"][bd[0]] = float(bd[1])
                        
                from flask import jsonify
                return jsonify(data)
        except Exception as e:
            return str(e)

    app_instance.add_url_rule("/dump_players_json_temp", "dump_players_json_temp", dump_players_json_temp, methods=["GET"])
    app_instance.add_url_rule("/spawn_economy_dede_temp", "spawn_economy_dede", spawn_economy_dede, methods=["GET"])
    app_instance.add_url_rule(
        "/reset_password_recovery_key",
        "reset_password_recovery_key",
        reset_password_recovery_key,
        methods=["POST"],
    )
