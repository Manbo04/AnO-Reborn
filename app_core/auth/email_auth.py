from flask import Blueprint, request, render_template, session, redirect, flash
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_request_cursor
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


def _password_matches(stored_hash, password: str) -> bool:
    """Check werkzeug or bcrypt password hashes."""
    if not stored_hash or not isinstance(stored_hash, str):
        return False

    if stored_hash.startswith(("scrypt:", "pbkdf2:sha256:")):
        return check_password_hash(stored_hash, password)

    try:
        import bcrypt

        return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
    except Exception:
        return False


def _complete_email_login(user_id, is_verified, has_verification, email):
    from email_utils import is_email_configured

    try:
        email_enforced = is_email_configured()
    except Exception:
        email_enforced = False

    if email_enforced and has_verification and is_verified is False:
        return redirect(f"/verification_pending?email={email}")

    session["user_id"] = user_id
    return redirect("/")


@email_auth_bp.route("/register/email", methods=["POST"])
def register_email():
    username = request.form.get("username")
    email = request.form.get("email")
    password = request.form.get("password")
    confirmation = request.form.get("confirmation")

    if not username or not email or not password or not confirmation:
        flash("All fields are required.")
        return redirect("/signup")

    if password != confirmation:
        flash("Passwords do not match.")
        return redirect("/signup")

    hashed_password = generate_password_hash(password)
    continent_str = request.form.get("continent", "1")
    try:
        continent_number = int(continent_str) - 1
    except ValueError:
        continent_number = 0
    continents = ["Tundra", "Savanna", "Desert", "Jungle", "Boreal Forest", "Grassland", "Mountain Range"]
    continent = continents[continent_number] if 0 <= continent_number < len(continents) else continents[0]

    with get_request_cursor() as db:
        db.execute("SELECT id FROM users WHERE username=%s OR email=%s", (username, email))
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

        verification_token = None
        from email_utils import is_email_configured, generate_verification_token, send_verification_email
        if cols["has_verification"] and is_email_configured():
            verification_token = generate_verification_token(email)
            insert_cols += ", is_verified, verification_token, token_created_at"
            insert_vals += ", %s, %s, NOW()"
            params.extend([False, verification_token])

        insert_vals += ")"

        db.execute(f"INSERT INTO users ({insert_cols}) VALUES {insert_vals} RETURNING id", params)
        user_id = db.fetchone()[0]

        if verification_token and is_email_configured():
            send_verification_email(email, username, verification_token)

        from signup import init_user_game_data
        init_user_game_data(db, user_id, continent)

    if verification_token:
        return redirect(f"/verification_pending?email={email}")
    session["user_id"] = user_id
    return redirect("/")


@email_auth_bp.route("/login/email", methods=["POST"])
def login_email():
    email = (request.form.get("email") or "").strip()
    password = request.form.get("password")

    if not email or not password:
        flash("Email and password are required.")
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
                f"SELECT {', '.join(select_cols)} FROM users WHERE email=%s",
                (email,),
            )
            row = db.fetchone()

        if not row:
            flash("Invalid email or password.")
            return redirect("/login")

        row_map = dict(zip(select_cols, row))
        user_id = row_map["id"]
        is_verified = row_map.get("is_verified")

        hash_candidates = []
        if cols["has_hash"] and row_map.get("hash"):
            hash_candidates.append(row_map["hash"])
        if cols["has_password"] and row_map.get("password"):
            hash_candidates.append(row_map["password"])

        for stored_hash in hash_candidates:
            if _password_matches(stored_hash, password):
                return _complete_email_login(
                    user_id,
                    is_verified,
                    cols["has_verification"],
                    email,
                )

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
