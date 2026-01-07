from flask import request, render_template, session, redirect, jsonify, current_app
from helpers import error

# Game.ping() # temporarily removed this line because it might make celery not work
# NOTE: 'app' is NOT imported at module level to avoid circular imports
import bcrypt
import os
from requests_oauthlib import OAuth2Session
from dotenv import load_dotenv
import datetime
from database import get_db_cursor

load_dotenv()


def login():
    if request.method == "POST":
        import logging

        logger = logging.getLogger(__name__)
        logger.debug("POST /login/ called")
        logger.debug("Login: request.form contains keys: %s", list(request.form.keys()))
        # Use application context to avoid circular imports / NameError
        current_app.config["SESSION_PERMANENT"] = True
        current_app.permanent_session_lifetime = datetime.timedelta(days=365)

        # gets the password input from the form
        password = request.form.get("password")
        # gets the username input from the forms
        username = request.form.get("username")
        logger.debug(
            f"Received form data: username={username}, password_set={bool(password)}"
        )

        if not username or not password:  # checks if inputs are blank
            logger.debug("Missing username or password")
            return error(400, "No Password or Username")

        password = password.encode("utf-8")

        with get_db_cursor() as db:
            # selects data about user, from users
            db.execute(
                "SELECT * FROM users WHERE username=(%s) AND auth_type='normal'",
                (username,),
            )
            user = db.fetchone()
            logger.debug(f"DB user row fetched for username={username}: {bool(user)}")

            try:
                hashed_pw = user[4].encode("utf-8")
                logger.debug("hashed_pw retrieved for user")
            except Exception as e:
                logger.debug(f"Exception getting hashed_pw: {e}")
                return error(403, "Wrong password or user doesn't exist")

            # checks if user exists and if the password is correct
            if bcrypt.checkpw(password, hashed_pw):
                logger.debug("Password matches, logging in user.")
                # sets session's user_id to current user's id
                session["user_id"] = user[0]
                logger.debug(f"Session after set: {dict(session)}")
                # Mark session as permanent and modified to ensure cookie is set on response
                session.permanent = True
                session.modified = True

                # TODO: remove later, this is for old users
                try:
                    db.execute(
                        "SELECT education, soldiers FROM policies WHERE user_id=%s",
                        (user[0],),
                    )
                except Exception:
                    db.execute("INSERT INTO policies (user_id) VALUES (%s)", (user[0],))

                logger.debug("Returning redirect to / after login")
                from flask import make_response

                response = redirect("/")
                return response  # redirects user to homepage
            else:
                logger.debug("Password does not match.")
                return error(400, "Wrong password")

    else:
        # renders login.html when "/login" is acessed via get
        return render_template("login.html")


OAUTH2_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
OAUTH2_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")

environment = os.getenv("ENVIRONMENT", "DEV")

if environment == "PROD":
    OAUTH2_REDIRECT_URI = "https://www.affairsandorder.com/callback"
else:
    OAUTH2_REDIRECT_URI = "http://localhost:5000/callback"

API_BASE_URL = os.environ.get("API_BASE_URL", "https://discordapp.com/api")
AUTHORIZATION_BASE_URL = API_BASE_URL + "/oauth2/authorize"
TOKEN_URL = API_BASE_URL + "/oauth2/token"

# NOTE: SECRET_KEY configuration moved to app.py after app initialization
# to avoid circular imports

if "http://" in OAUTH2_REDIRECT_URI:
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "true"


def token_updater(token):
    session["oauth2_token"] = token


def make_session(token=None, state=None, scope=None):
    return OAuth2Session(
        client_id=OAUTH2_CLIENT_ID,
        token=token,
        state=state,
        scope=scope,
        redirect_uri=OAUTH2_REDIRECT_URI,
        auto_refresh_kwargs={
            "client_id": OAUTH2_CLIENT_ID,
            "client_secret": OAUTH2_CLIENT_SECRET,
        },
        auto_refresh_url=TOKEN_URL,
        token_updater=token_updater,
    )


def discord_login():
    from app import app
    app.config["SESSION_PERMANENT"] = True
    app.permanent_session_lifetime = datetime.timedelta(days=365)

    with get_db_cursor() as db:
        discord = make_session(token=session.get("oauth2_token"))
        discord_user_id = discord.get(API_BASE_URL + "/users/@me").json()["id"]

        discord_auth = discord_user_id

        db.execute(
            "SELECT id FROM users WHERE hash=(%s) AND auth_type='discord'",
            (discord_auth,),
        )
        user_id = db.fetchone()[0]

        # TODO: remove later, this is for old users
        try:
            db.execute(
                "SELECT education, soldiers FROM policies WHERE user_id=%s", (user_id,)
            )
        except Exception:
            db.execute("INSERT INTO policies (user_id) VALUES (%s)", (user_id,))

    session["user_id"] = user_id  # clears session variables from oauth
    session.permanent = True
    session.modified = True
    try:
        session.pop("oauth2_state")
    except KeyError:
        pass

    session.pop("oauth2_token")

    return redirect("/")


# NOTE: developer-only debug endpoints `_debug_login` and `_force_set_cookie`
# were intentionally removed during cleanup. If you need to temporarily
# re-enable explicit cookie/ session diagnostics, add a guarded endpoint
# behind a config flag (e.g. app.config['ENABLE_DEV_ENDPOINTS'] == True).


def register_login_routes(app_instance):
    """Register login routes. Called by app.py after app initialization."""
    app_instance.add_url_rule("/login/", "login_slash", login, methods=["GET", "POST"])
    app_instance.add_url_rule("/login", "login", login, methods=["GET", "POST"])
    app_instance.add_url_rule("/discord_login/", "discord_login", discord_login, methods=["GET"])
