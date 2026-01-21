from flask import request, render_template, session, redirect, flash
from helpers import login_required, error
# NOTE: 'app' is NOT imported at module level to avoid circular imports
import os
from dotenv import load_dotenv
import bcrypt
from string import ascii_uppercase, ascii_lowercase, digits
from datetime import datetime
from random import SystemRandom
from database import get_db_cursor

load_dotenv()

import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail


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


def sendEmail(recipient, code):
    url = generateUrlFromCode(code)
    import logging

    logger = logging.getLogger(__name__)

    message = Mail(
        from_email=os.getenv("MAIL_USERNAME"),
        to_emails=recipient,
        subject="Affairs & Order | Password change request",
        html_content=f"Click this URL and complete further steps to change your password. {url}. If you did not request a password change, ignore this email.",
    )
    try:
        sg = SendGridAPIClient(os.getenv("SENDGRID_API_KEY"))
        response = sg.send(message)
        logger.info(f"Email sent: {response.status_code}")
    except Exception as e:
        logger.error(f"Failed to send email: {str(e)}")


# Route for requesting the reset of a password, after which the user can reset his password.
def request_password_reset():
    code = generateResetCode()

    with get_db_cursor() as db:
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
                return redirect("/")
            cId = result[0]

        # Insert reset code record for the user (always)
        db.execute(
            "INSERT INTO reset_codes (url_code, user_id, created_at) VALUES (%s, %s, %s)",
            (code, cId, int(datetime.now().timestamp())),
        )

    # Send email with reset link regardless of how request was initiated
    if email:
        try:
            sendEmail(email, code)
        except Exception:
            # Log failures but don't reveal to user
            pass

    # Redirect to a neutral page (home) so attackers cannot probe for valid emails
    return redirect("/")


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
            return error(400, "No password provided.")
        if len(new_password_raw) < 6:
            return error(400, "Password must be at least 6 characters long.")

        new_password = new_password_raw.encode("utf-8")

        try:
            with get_db_cursor() as db:
                logger.debug(f"Received URL code: {code}")
                db.execute("SELECT user_id FROM reset_codes WHERE url_code=%s", (code,))
                result = db.fetchone()
                if not result:
                    return error(400, "Invalid or expired reset code.")
                user_id = result[0]

                hashed = bcrypt.hashpw(new_password, bcrypt.gensalt(14)).decode("utf-8")
                db.execute("UPDATE users SET hash=%s WHERE id=%s", (hashed, user_id))
                db.execute("DELETE FROM reset_codes WHERE url_code=%s", (code,))
        except Exception as e:
            logger.exception(f"Error resetting password for code {code}: {e}")
            return error(500, "An error occurred while resetting your password. Please try again later.")

        return redirect("/")


@login_required
def change():
    with get_db_cursor() as db:
        cId = session["user_id"]

        password = request.form.get("current_password").encode("utf-8")
        email = request.form.get("email")
        name = request.form.get("name")

        if not password:
            return error(400, "No password provided")

        db.execute("SELECT hash FROM users WHERE id=%s", (cId,))
        hash_value = db.fetchone()[0].encode("utf-8")

        if bcrypt.checkpw(password, hash_value):
            if email:
                db.execute("UPDATE users SET email=%s WHERE id=%s", (email, cId))
            if name:
                db.execute("UPDATE users SET username=%s WHERE id=%s", (name, cId))
        else:
            return error(401, "Incorrect password")

    return redirect("/account")


def register_change_routes(app_instance):
    """Register all change routes with the Flask app instance"""
    app_instance.add_url_rule("/request_password_reset", "request_password_reset", request_password_reset, methods=["POST"])
    app_instance.add_url_rule("/reset_password/<code>", "reset_password", reset_password, methods=["GET", "POST"])
    app_instance.add_url_rule("/change", "change", change, methods=["POST"])
