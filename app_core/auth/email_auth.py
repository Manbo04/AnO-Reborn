from flask import Blueprint, request, render_template, session, redirect, flash
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_request_cursor
import datetime
import logging

logger = logging.getLogger(__name__)

email_auth_bp = Blueprint('email_auth', __name__)

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

        db.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'users' AND column_name IN ('hash', 'password')")
        cols = [r[0] for r in db.fetchall()]
        
        db.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'is_verified'")
        has_verification = db.fetchone() is not None
        
        insert_cols = "username, email, date, auth_type"
        insert_vals = "(%s, %s, %s, %s"
        params = [username, email, str(datetime.date.today()), "email"]
        
        if "hash" in cols:
            insert_cols += ", hash"
            insert_vals += ", %s"
            params.append(hashed_password)
        if "password" in cols:
            insert_cols += ", password"
            insert_vals += ", %s"
            params.append(hashed_password)
            
        verification_token = None
        from email_utils import is_email_configured, generate_verification_token, send_verification_email
        if has_verification and is_email_configured():
            verification_token = generate_verification_token(email)
            insert_cols += ", is_verified, verification_token, token_created_at"
            insert_vals += ", %s, %s, NOW()"
            params.extend([False, verification_token])
            
        insert_vals += ")"
        
        db.execute(f"INSERT INTO users ({insert_cols}) VALUES {insert_vals} RETURNING id", params)
        user_id = db.fetchone()[0]

        if verification_token and is_email_configured():
            send_verification_email(email, username, verification_token)

        db.execute("INSERT INTO stats (id, location) VALUES (%s, %s) ON CONFLICT DO NOTHING", (user_id, continent))
        db.execute("INSERT INTO policies (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,))
        from signup import _init_economy_tables
        _init_economy_tables(db, user_id)
        
    if verification_token:
        return redirect(f"/verification_pending?email={email}")
    else:
        session["user_id"] = user_id
        return redirect("/")

@email_auth_bp.route("/login/email", methods=["POST"])
def login_email():
    email = request.form.get("email")
    password = request.form.get("password")

    if not email or not password:
        flash("Email and password are required.")
        return redirect("/login")

    with get_request_cursor() as db:
        db.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'users' AND column_name IN ('hash', 'password')")
        cols = [r[0] for r in db.fetchall()]
        
        sel_cols = "id, is_verified"
        if "hash" in cols: sel_cols += ", hash"
        if "password" in cols: sel_cols += ", password"
        
        db.execute(f"SELECT {sel_cols} FROM users WHERE email=%s", (email,))
        user = db.fetchone()

    if not user:
        flash("Invalid email or password.")
        return redirect("/login")

    user_id = user[0]
    
    hash_idx = 1 if "hash" in cols else -1
    pw_idx = 2 if "hash" in cols and "password" in cols else (1 if "password" in cols else -1)
    
    hash_val = user[hash_idx] if hash_idx != -1 else None
    password_val = user[pw_idx] if pw_idx != -1 else None
    
    # Try werkzeug hash
    for val in (hash_val, password_val):
        if val and val.startswith('scrypt:'):
            if check_password_hash(val, password):
                from email_utils import is_email_configured
                try:
                    email_enforced = is_email_configured()
                except Exception:
                    email_enforced = False

                if email_enforced:
                    is_verified = user[1] # is_verified is 2nd column
                    if is_verified is False:
                        return redirect(f"/verification_pending?email={email}")

                session["user_id"] = user_id
                return redirect("/")
        elif val and val.startswith('pbkdf2:sha256:'):
            if check_password_hash(val, password):
                from email_utils import is_email_configured
                try:
                    email_enforced = is_email_configured()
                except Exception:
                    email_enforced = False

                if email_enforced:
                    is_verified = user[1] # is_verified is 2nd column
                    if is_verified is False:
                        return redirect(f"/verification_pending?email={email}")

                session["user_id"] = user_id
                return redirect("/")
    
    # Fallback to bcrypt
    import bcrypt
    pwd_bytes = password.encode('utf-8')
    for val in (hash_val, password_val):
        if val:
            try:
                if bcrypt.checkpw(pwd_bytes, val.encode('utf-8')):
                    session["user_id"] = user_id
                    return redirect("/")
            except Exception:
                pass

    flash("Invalid email or password.")
    return redirect("/login")
