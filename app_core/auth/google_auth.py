import os
import datetime
import logging
from flask import request, session, redirect, current_app, flash, render_template
from requests_oauthlib import OAuth2Session
from dotenv import load_dotenv
from helpers import error

load_dotenv()
logger = logging.getLogger(__name__)

def is_google_auth_configured() -> bool:
    return bool(
        os.environ.get("GOOGLE_CLIENT_ID", "").strip()
        and os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
    )


def _google_client_id() -> str:
    return os.environ.get("GOOGLE_CLIENT_ID", "").strip()


def _google_client_secret() -> str:
    return os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()


def get_google_redirect_uri() -> str:
    """OAuth callback URL — override with GOOGLE_REDIRECT_URI on any environment."""
    explicit = os.environ.get("GOOGLE_REDIRECT_URI", "").strip()
    if explicit:
        return explicit
    if os.environ.get("RAILWAY_STATIC_URL") or os.environ.get("RAILWAY_ENVIRONMENT_NAME"):
        return "https://affairsandorder.com/login/google/callback"
    return "http://127.0.0.1:5000/login/google/callback"


AUTHORIZATION_BASE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

if "http://" in get_google_redirect_uri():
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"


def make_google_session(token=None, state=None):
    return OAuth2Session(
        client_id=_google_client_id(),
        token=token,
        state=state,
        scope=["openid", "email", "profile"],
        redirect_uri=get_google_redirect_uri(),
    )

def google_login_route():
    if not is_google_auth_configured():
        flash("Google login is not configured.")
        return redirect("/login")
    
    intent = request.args.get("intent", "login")
    google = make_google_session()
    authorization_url, state = google.authorization_url(
        AUTHORIZATION_BASE_URL,
        access_type="offline",
        prompt="select_account"
    )
    session["google_oauth2_state"] = state
    session["google_oauth2_intent"] = intent
    return redirect(authorization_url)

def google_callback_route():
    from database import get_request_cursor

    if request.values.get("error"):
        flash("Google login failed or was cancelled.")
        return redirect("/login")

    state = session.get("google_oauth2_state")
    if not state:
        flash("Google login session expired. Please try again.")
        return redirect("/login")

    google = make_google_session(state=state)
    try:
        token = google.fetch_token(
            TOKEN_URL,
            client_secret=_google_client_secret(),
            authorization_response=request.url,
        )
        session["google_oauth2_token"] = token
    except Exception as e:
        redirect_uri = get_google_redirect_uri()
        logger.error(
            "Google fetch token error (redirect_uri=%s): %s",
            redirect_uri,
            e,
        )
        err_text = str(e).lower()
        if "redirect_uri_mismatch" in err_text or "redirect uri" in err_text:
            flash(
                "Google login failed: redirect URI mismatch. "
                f"Ensure Google Cloud allows: {redirect_uri}"
            )
        else:
            flash("Failed to retrieve token from Google.")
        return redirect("/login")

    try:
        google_api = make_google_session(token=token)
        user_info = google_api.get(USERINFO_URL).json()
    except Exception as e:
        logger.error(f"Google fetch user info error: {e}")
        flash("Failed to fetch user information from Google.")
        return redirect("/login")

    google_user_id = user_info.get("sub")
    email = user_info.get("email")

    if not google_user_id:
        flash("Invalid user info returned from Google.")
        return redirect("/login")

    session['google_email'] = email
    intent = session.pop("google_oauth2_intent", "login")
    
    with get_request_cursor() as db:
        # Check if user exists
        db.execute(
            "SELECT id FROM users WHERE hash=%s AND auth_type='google' LIMIT 1",
            (google_user_id,),
        )
        user = db.fetchone()

        if user:
            # User exists, log them in
            session["user_id"] = user[0]
            current_app.config["SESSION_PERMANENT"] = True
            current_app.permanent_session_lifetime = datetime.timedelta(days=365)
            session.permanent = True
            session.modified = True
            
            # Clean up
            session.pop("google_oauth2_state", None)
            session.pop("google_oauth2_token", None)
            return redirect("/")
        else:
            # User does not exist, go to signup
            return redirect("/google_signup")

def google_signup_route():
    from database import get_request_cursor
    from signup import ensure_signup_attempts_table, _init_economy_tables

    if request.method == "GET":
        from app_core.referrals.service import capture_referral_from_request

        referral_invite = capture_referral_from_request()
        recaptcha_site_key = os.getenv("RECAPTCHA_SITE_KEY", "")
        return render_template(
            "signup.html",
            way="google",
            recaptcha_site_key=recaptcha_site_key,
            referral_invite=referral_invite,
        )

    elif request.method == "POST":
        try:
            ensure_signup_attempts_table()
            
            # IP Rate Limiting
            forwarded = request.headers.get("X-Forwarded-For") or request.headers.get(
                "X-Forwarded-For".lower()
            )
            client_ip = forwarded.split(",")[0].strip() if forwarded else request.remote_addr

            with get_request_cursor() as db:
                db.execute(
                    "SELECT COUNT(*) FROM signup_attempts WHERE ip_address = %s AND attempt_time >= NOW() - INTERVAL '1 day'",
                    (client_ip,),
                )
                attempt_row = db.fetchone()
                attempt_count = attempt_row[0] if attempt_row else 0
                if attempt_count >= 10:
                    return error(429, "Too many signup attempts from this IP. Please try again tomorrow.")

                db.execute("INSERT INTO signup_attempts (ip_address) VALUES (%s)", (client_ip,))

            # Google Session Validation
            oauth_token = session.get("google_oauth2_token")
            if not oauth_token:
                flash("Google signup session expired. Please click Google Sign Up again.")
                return redirect("/signup")

            google_api = make_google_session(token=oauth_token)
            user_info = google_api.get(USERINFO_URL).json()
            google_user_id = user_info.get("sub")
            email = user_info.get("email")

            if not google_user_id:
                flash("Could not fetch Google profile.")
                return redirect("/signup")

            username = request.form.get("username", "").strip()
            continent_str = request.form.get("continent")
            
            if not username or not continent_str:
                return error(400, "Missing fields")

            if len(username) > 20:
                return error(400, "Country name cannot exceed 20 characters")

            try:
                continent_number = int(continent_str) - 1
                continents = [
                    "Tundra", "Savanna", "Desert", "Jungle",
                    "Boreal Forest", "Grassland", "Mountain Range",
                ]
                continent = continents[continent_number]
            except (ValueError, IndexError):
                return error(400, "Invalid biome selection")

            # Create account
            with get_request_cursor() as db:
                db.execute("SELECT id FROM users WHERE username=%s", (username,))
                if db.fetchone():
                    return error(400, "Country name already taken")

                if email:
                    db.execute("SELECT id FROM users WHERE email=%s", (email,))
                    if db.fetchone():
                        return error(400, "An account with this email already exists")

                db.execute("SELECT id FROM users WHERE hash=%s AND auth_type='google'", (str(google_user_id),))
                if db.fetchone():
                    return error(400, "This Google account is already linked to another country")

                date = str(datetime.date.today())
                db.execute(
                    "INSERT INTO users (username, email, hash, date, auth_type, is_verified) VALUES (%s, %s, %s, %s, %s, %s)",
                    (username, email, str(google_user_id), date, "google", True),
                )

                db.execute("SELECT id FROM users WHERE hash=%s AND auth_type='google'", (str(google_user_id),))
                google_user_row = db.fetchone()
                if not google_user_row:
                    return error(500, "Signup failed: could not create user")
                user_id = google_user_row[0]

                session["user_id"] = user_id
                current_app.config["SESSION_PERMANENT"] = True
                current_app.permanent_session_lifetime = datetime.timedelta(days=365)
                session.permanent = True
                session.modified = True

                from signup import _complete_referral_signup, init_user_game_data

                init_user_game_data(db, user_id, continent)
                _complete_referral_signup(db, user_id)

                db.execute(
                    "UPDATE signup_attempts SET successful = TRUE WHERE id = (SELECT id FROM signup_attempts WHERE ip_address = %s ORDER BY attempt_time DESC LIMIT 1)",
                    (client_ip,),
                )

            session.pop("google_oauth2_state", None)
            session.pop("google_oauth2_token", None)
            session.pop("google_email", None)

            from app_core.onboarding.service import post_signup_redirect

            return redirect(post_signup_redirect(user_id))

        except Exception as e:
            logger.exception(f"Google signup error: {e}")
            return error(500, f"Signup failed: {str(e)}")

def register_google_auth_routes(app):
    app.add_url_rule("/login/google", "google_login", google_login_route, methods=["GET"])
    app.add_url_rule("/login/google/callback", "google_callback", google_callback_route, methods=["GET"])
    app.add_url_rule("/google_signup", "google_signup", google_signup_route, methods=["GET", "POST"])

