from flask import request, render_template, session, redirect
from helpers import error
# Game.ping() # temporarily removed this line because it might make celery not work
from app import app
import bcrypt
import os
from requests_oauthlib import OAuth2Session
from dotenv import load_dotenv
import datetime
from database import get_db_cursor
load_dotenv()

@app.route("/login/", methods=["GET", "POST"])
def login():

    if request.method == "POST":
        import logging
        logger = logging.getLogger(__name__)
        logger.error("[DEBUG] POST /login/ called")
        app.config["SESSION_PERMANENT"] = True
        app.permanent_session_lifetime = datetime.timedelta(days=365)

        # gets the password input from the form
        password = request.form.get("password")
        # gets the username input from the forms
        username = request.form.get("username")
        logger.error(f"[DEBUG] username: {username}, password: {password}")

        if not username or not password:  # checks if inputs are blank
            logger.error("[DEBUG] Missing username or password")
            return error(400, "No Password or Username")

        password = password.encode("utf-8")

        with get_db_cursor() as db:
            # selects data about user, from users
            db.execute("SELECT * FROM users WHERE username=(%s) AND auth_type='normal'", (username,))
            user = db.fetchone()
            logger.error(f"[DEBUG] DB user row: {user}")

            try:
                hashed_pw = user[4].encode("utf-8")
                logger.error(f"[DEBUG] hashed_pw: {hashed_pw}")
            except Exception as e:
                logger.error(f"[DEBUG] Exception getting hashed_pw: {e}")
                return error(403, "Wrong password or user doesn't exist")

            # checks if user exists and if the password is correct
            if bcrypt.checkpw(password, hashed_pw):
                logger.error("[DEBUG] Password matches, logging in user.")
                # sets session's user_id to current user's id
                session["user_id"] = user[0]

                # TODO: remove later, this is for old users
                try:
                    db.execute("SELECT education, soldiers FROM policies WHERE user_id=%s", (user[0],))
                except Exception:
                    db.execute("INSERT INTO policies (user_id) VALUES (%s)", (user[0],))

                return redirect("/")  # redirects user to homepage
            else:
                logger.error("[DEBUG] Password does not match.")
                return error(400, "Wrong password")

    else:
        # renders login.html when "/login" is acessed via get
        return render_template("login.html")

OAUTH2_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
OAUTH2_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")

environment = os.getenv("ENVIRONMENT", "DEV")

if environment == "PROD":
    OAUTH2_REDIRECT_URI = 'https://www.affairsandorder.com/callback'
else:
    OAUTH2_REDIRECT_URI = 'http://localhost:5000/callback'

API_BASE_URL = os.environ.get('API_BASE_URL', 'https://discordapp.com/api')
AUTHORIZATION_BASE_URL = API_BASE_URL + '/oauth2/authorize'
TOKEN_URL = API_BASE_URL + '/oauth2/token'

app.config['SECRET_KEY'] = OAUTH2_CLIENT_SECRET

if 'http://' in OAUTH2_REDIRECT_URI:
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = 'true'

def token_updater(token):
    session['oauth2_token'] = token
    
def make_session(token=None, state=None, scope=None):
    return OAuth2Session(
        client_id=OAUTH2_CLIENT_ID,
        token=token,
        state=state,
        scope=scope,
        redirect_uri=OAUTH2_REDIRECT_URI,
        auto_refresh_kwargs={
            'client_id': OAUTH2_CLIENT_ID,
            'client_secret': OAUTH2_CLIENT_SECRET,
        },
        auto_refresh_url=TOKEN_URL,

        token_updater=token_updater)

@app.route('/discord_login/', methods=["GET"])
def discord_login():

    app.config["SESSION_PERMANENT"] = True
    app.permanent_session_lifetime = datetime.timedelta(days=365)

    with get_db_cursor() as db:
        discord = make_session(token=session.get('oauth2_token'))
        discord_user_id = discord.get(API_BASE_URL + '/users/@me').json()['id']

        discord_auth = discord_user_id

        db.execute("SELECT id FROM users WHERE hash=(%s) AND auth_type='discord'", (discord_auth,))
        user_id = db.fetchone()[0]

        # TODO: remove later, this is for old users
        try:
            db.execute("SELECT education, soldiers FROM policies WHERE user_id=%s", (user_id,))
        except Exception:
            db.execute("INSERT INTO policies (user_id) VALUES (%s)", (user_id,))

    session['user_id'] = user_id    # clears session variables from oauth
    try:
        session.pop('oauth2_state')
    except KeyError:
        pass

    session.pop('oauth2_token')

    return redirect("/")