import os
import re
from flask import Blueprint, request, render_template, session, redirect, flash
from app_core.auth.passwords import hash_password, password_matches
from database import get_request_cursor, client_ip_from_headers, coarse_fingerprint_from_headers
from login_verification import complete_or_verify_login
from signup import verify_recaptcha
import datetime
import logging

logger = logging.getLogger(__name__)

email_auth_bp = Blueprint('email_auth', __name__)


def _users_auth_columns(db):
    """Return which credential / verification columns exist on users."""
    db.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'users'
          AND column_name IN ('hash', 'password', 'is_verified')
        """
    )
    found = {row[0] for row in db.fetchall()}
    return {
        "has_hash": "hash" in found,
        "has_password": "password" in found,
        "has_verification": "is_verified" in found,
    }


def _complete_email_login(user_id, is_verified, has_verification, email):
    from email_utils import is_email_configured

    try:
        email_enforced = is_email_configured()
    except Exception:
        email_enforced = False

    if email_enforced and has_verification and is_verified is False and os.getenv("REQUIRE_EMAIL_VERIFICATION") == "1":
        import urllib.parse
        safe_email = urllib.parse.quote(email)
        return redirect(f"/verification_pending?email={safe_email}")

    from app_core.auth.totp import has_2fa_enabled

    if has_2fa_enabled(user_id):
        # Same second-factor gate as /login and the Discord/Google paths:
        # a correct password alone must not open a 2FA-protected account.
        import time

        session.clear()
        session["pending_2fa_user_id"] = user_id
        session["pending_2fa_auth_type"] = "email"
        session["pending_2fa_started_at"] = time.time()
        session.permanent = True
        return redirect("/login/2fa")

    ip = client_ip_from_headers(request.headers, request.remote_addr)
    fingerprint = coarse_fingerprint_from_headers(request.headers)
    return complete_or_verify_login(user_id, ip, fingerprint, "email")


_USERNAME_MIN, _USERNAME_MAX = 3, 30
_USERNAME_EXTRA_CHARS = set(" _-.'")
_EMAIL_RE = re.compile(r"^[^@\s<>\"']+@[^@\s<>\"']+\.[^@\s<>\"']+$")
SIGNUP_MAX_ATTEMPTS_PER_IP_PER_DAY = 10


def validate_username(username: str) -> str | None:
    """Return an error message, or None if the nation name is acceptable.
    Names are rendered all over the game, so only letters/digits and a few
    separators are allowed (no markup characters, control chars or blanks)."""
    if not (_USERNAME_MIN <= len(username) <= _USERNAME_MAX):
        return f"Nation name must be {_USERNAME_MIN}-{_USERNAME_MAX} characters."
    if username != username.strip() or "  " in username:
        return "Nation name cannot start/end with a space or contain double spaces."
    if not all(ch.isalnum() or ch in _USERNAME_EXTRA_CHARS for ch in username):
        return "Nation name may only contain letters, numbers, spaces and _ - . '"
    if not any(ch.isalnum() for ch in username):
        return "Nation name must contain a letter or number."
    return None


def _signup_ip_rate_limited(db) -> bool:
    """Per-IP daily cap shared with /signup (signup_attempts table). Loopback
    is exempt so local/test runs are not throttled. Records this attempt."""
    from helpers import client_ip_from_request

    ip = client_ip_from_request()
    if ip and (ip.startswith("127.") or ip in ("::1", "::ffff:127.0.0.1")):
        return False
    db.execute("SAVEPOINT signup_rate_check")
    try:
        db.execute(
            "SELECT COUNT(*) FROM signup_attempts "
            "WHERE ip_address = %s AND attempt_time >= NOW() - INTERVAL '1 day'",
            (ip or "unknown",),
        )
        row = db.fetchone()
        if row and int(row[0] or 0) >= SIGNUP_MAX_ATTEMPTS_PER_IP_PER_DAY:
            db.execute("RELEASE SAVEPOINT signup_rate_check")
            return True
        db.execute(
            "INSERT INTO signup_attempts (ip_address, ip, attempt_time, successful) "
            "VALUES (COALESCE(%s, 'unknown'), COALESCE(%s, 'unknown'), NOW(), FALSE)",
            (ip, ip),
        )
        db.execute("RELEASE SAVEPOINT signup_rate_check")
    except Exception:
        # Never block signups because the counter table misbehaved.
        logger.exception("signup rate-limit check failed")
        db.execute("ROLLBACK TO SAVEPOINT signup_rate_check")
    return False


@email_auth_bp.route("/register/email", methods=["POST"])
def register_email():
    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password")
    confirmation = request.form.get("confirmation")

    if not username or not email or not password or not confirmation:
        flash("All fields are required.")
        return redirect("/signup")

    if not verify_recaptcha(request.form.get("g-recaptcha-response")):
        flash("Please complete the captcha check and try again.")
        return redirect("/signup")

    if not request.form.get("terms_agree"):
        flash("You must agree to the Terms of Service and Privacy Policy.")
        return redirect("/signup")

    name_error = validate_username(username)
    if name_error:
        flash(name_error)
        return redirect("/signup")

    if len(email) > 100 or not _EMAIL_RE.match(email):
        flash("Invalid email format.")
        return redirect("/signup")

    if password != confirmation:
        flash("Passwords do not match.")
        return redirect("/signup")

    if len(password) < 8 or len(password.encode("utf-8")) > 72:
        flash("Password must be 8-72 characters.")
        return redirect("/signup")

    hashed_password = hash_password(password)
    continent_str = request.form.get("continent", "1")
    try:
        continent_number = int(continent_str) - 1
    except ValueError:
        continent_number = 0
    continents = ["Tundra", "Savanna", "Desert", "Jungle", "Boreal Forest", "Grassland", "Mountain Range"]
    continent = continents[continent_number] if 0 <= continent_number < len(continents) else continents[0]

    verification_token = None
    try:
        with get_request_cursor() as db:
            if _signup_ip_rate_limited(db):
                flash("Too many signup attempts from this network. Please try again tomorrow.")
                return redirect("/signup")

            db.execute(
                "SELECT id FROM users WHERE LOWER(username)=LOWER(%s) OR LOWER(email)=LOWER(%s)",
                (username, email),
            )
            if db.fetchone():
                flash("Username or email already taken.")
                return redirect("/signup")

            cols = _users_auth_columns(db)

            insert_cols = "username, email, date, auth_type"
            insert_vals = "(%s, %s, %s, %s"
            params = [username, email, str(datetime.date.today()), "email"]

            if cols["has_hash"]:
                insert_cols += ", hash"
                insert_vals += ", %s"
                params.append(hashed_password)
            if cols["has_password"]:
                insert_cols += ", password"
                insert_vals += ", %s"
                params.append(hashed_password)

            from email_utils import is_email_configured, generate_verification_token, send_verification_email
            if cols["has_verification"] and is_email_configured():
                verification_token = generate_verification_token(email)
                insert_cols += ", is_verified, verification_token, token_created_at"
                insert_vals += ", %s, %s, NOW()"
                params.extend([False, verification_token])

            insert_vals += ")"

            db.execute(f"INSERT INTO users ({insert_cols}) VALUES {insert_vals} RETURNING id", params)
            user_id = db.fetchone()[0]

            from signup import _complete_referral_signup, init_user_game_data

            init_user_game_data(db, user_id, continent)
            _complete_referral_signup(db, user_id)
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        flash("An internal error occurred during registration. Please try again later.")
        return redirect("/signup")

    if verification_token and is_email_configured():
        send_verification_email(email, username, verification_token)
        if os.getenv("REQUIRE_EMAIL_VERIFICATION") == "1":
            import urllib.parse
            safe_email = urllib.parse.quote(email)
            return redirect(f"/verification_pending?email={safe_email}")

    from login_verification import establish_authenticated_session

    establish_authenticated_session(
        user_id,
        client_ip_from_headers(request.headers, request.remote_addr),
        coarse_fingerprint_from_headers(request.headers),
        "email",
    )
    from app_core.onboarding.service import post_signup_redirect

    return redirect(post_signup_redirect(user_id))


@email_auth_bp.route("/login/email", methods=["POST"])
def login_email():
    email = (request.form.get("email") or "").strip()
    password = request.form.get("password")

    if not email or not password:
        flash("Email and password are required.")
        return redirect("/login")

    recaptcha_response = request.form.get("g-recaptcha-response")
    if not verify_recaptcha(recaptcha_response):
        flash("Invalid email or password.")
        return redirect("/login")

    try:
        with get_request_cursor() as db:
            cols = _users_auth_columns(db)

            select_cols = ["id"]
            if cols["has_verification"]:
                select_cols.append("is_verified")
            if cols["has_hash"]:
                select_cols.append("hash")
            if cols["has_password"]:
                select_cols.append("password")

            db.execute(
                f"SELECT {', '.join(select_cols)} FROM users WHERE LOWER(email)=LOWER(%s)",
                (email,),
            )
            row = db.fetchone()

        if not row:
            flash("Invalid email or password.")
            return redirect("/login")

        row_map = dict(zip(select_cols, row))
        user_id = row_map["id"]
        is_verified = row_map.get("is_verified")

        from app_core.auth import lockout

        if lockout.password_locked(user_id):
            flash("Too many failed login attempts. Please try again in 15 minutes.")
            return redirect("/login")

        hash_candidates = []
        if cols["has_hash"] and row_map.get("hash"):
            hash_candidates.append(row_map["hash"])
        if cols["has_password"] and row_map.get("password"):
            hash_candidates.append(row_map["password"])

        for stored_hash in hash_candidates:
            if password_matches(stored_hash, password):
                lockout.password_clear(user_id)
                return _complete_email_login(
                    user_id,
                    is_verified,
                    cols["has_verification"],
                    email,
                )

        lockout.password_record_failure(user_id)
        flash("Invalid email or password.")
        return redirect("/login")
    except Exception as exc:
        import logging
        import uuid

        logger = logging.getLogger(__name__)
        event_id = f"{uuid.uuid4().hex[:8]}"
        logger.exception("login_email failed (id=%s): %s", event_id, exc)
        flash(
            "Login failed due to a server error. "
            f"Please try again or report id: {event_id}"
        )
        return redirect("/login")
