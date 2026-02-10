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


def sendEmail(recipient, code):
    url = generateUrlFromCode(code)
    import logging

    logger = logging.getLogger(__name__)

    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail
    except Exception:
        logger.error("SendGrid not available; skipping email send")
        return

    message = Mail(
        from_email=os.getenv("MAIL_USERNAME"),
        to_emails=recipient,
        subject="Affairs & Order | Password change request",
        html_content=(
            "Click this URL and complete further steps to change your password. "
            f"{url}. If you did not request a password change, ignore this email."
        ),
    )
    try:
        sg = SendGridAPIClient(os.getenv("SENDGRID_API_KEY"))
        response = sg.send(message)
        logger.info(f"Email sent: {response.status_code}")
    except Exception as e:
        logger.error(f"Failed to send email: {str(e)}")


# Route for requesting a password reset. After this, user can reset their password.
def request_password_reset():
    import logging

    logger = logging.getLogger(__name__)

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

    # Send email with reset link regardless of how request was initiated
    if email:
        try:
            sendEmail(email, code)
        except Exception:
            # Log failures but don't reveal to user
            pass

    # Inform user and redirect back to forgot password page
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
            with get_db_cursor() as db:
                logger.debug(f"Received URL code: {code}")
                db.execute("SELECT user_id FROM reset_codes WHERE url_code=%s", (code,))
                result = db.fetchone()
                if not result:
                    return error(400, "Invalid or expired reset code.")
                user_id = result[0]

                hashed = bcrypt.hashpw(new_password, bcrypt.gensalt(14)).decode("utf-8")
                db.execute(
                    "UPDATE users SET hash=%s WHERE id=%s",
                    (hashed, user_id),
                )
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
