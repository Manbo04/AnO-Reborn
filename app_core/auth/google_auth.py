from flask import request, session, redirect, current_app, flash, url_for
from requests_oauthlib import OAuth2Session
import os
from dotenv import load_dotenv
import logging
from database import get_request_cursor, users_table_has_column

load_dotenv()
logger = logging.getLogger(__name__)

# Google OAuth Configuration
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")

if "RAILWAY_STATIC_URL" in os.environ:
    GOOGLE_REDIRECT_URI = "https://affairsandorder.com/login/google/callback"
else:
    GOOGLE_REDIRECT_URI = os.environ.get(
        "GOOGLE_REDIRECT_URI", "http://localhost:5000/login/google/callback"
    )

AUTHORIZATION_BASE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"

if "http://" in GOOGLE_REDIRECT_URI:
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

def make_google_session(token=None, state=None):
    return OAuth2Session(
        client_id=GOOGLE_CLIENT_ID,
        token=token,
        state=state,
        scope=["openid", "email", "profile"],
        redirect_uri=GOOGLE_REDIRECT_URI,
    )

def google_login_route():
    if not GOOGLE_CLIENT_ID:
        flash("Google login is not configured on this server.")
        return redirect("/login")
    
    intent = request.args.get("intent", "login")
    google = make_google_session()
    # Google requires prompt="select_account" to show account chooser
    authorization_url, state = google.authorization_url(
        AUTHORIZATION_BASE_URL,
        access_type="offline",
        prompt="select_account"
    )
    session["google_oauth2_state"] = state
    session["google_oauth2_intent"] = intent
    return redirect(authorization_url)

def google_callback_route():
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
            client_secret=GOOGLE_CLIENT_SECRET,
            authorization_response=request.url,
        )
    except Exception as e:
        logger.error(f"Google fetch token error: {e}")
        flash("Failed to retrieve token from Google.")
        return redirect("/login")

    try:
        userinfo_url = "https://openidconnect.googleapis.com/v1/userinfo"
        user_info = google.get(userinfo_url).json()
    except Exception as e:
        logger.error(f"Google fetch user info error: {e}")
        flash("Failed to fetch user information from Google.")
        return redirect("/login")

    google_user_id = user_info.get("sub")
    email = user_info.get("email")

    if not google_user_id:
        flash("Invalid user info returned from Google.")
        return redirect("/login")

    intent = session.pop("google_oauth2_intent", "login")
    
    with get_request_cursor() as db:
        # Check if users table has google_id column, if not, wait.
        # But maybe we can just use the user's email if they registered using email?
        # Or if we want to store google_id, we should alter table.
        # Actually, wait, does the db have google_id? Let's check.
        # We will do this properly later.
        pass
    
    return redirect("/")

def register_google_auth_routes(app):
    app.add_url_rule("/login/google", "google_login", google_login_route, methods=["GET"])
    app.add_url_rule("/login/google/callback", "google_callback", google_callback_route, methods=["GET"])

