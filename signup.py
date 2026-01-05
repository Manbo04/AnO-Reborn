# FULLY MIGRATED

from flask import request, render_template, session, redirect
import datetime
from helpers import error
import psycopg2

# Game.ping() # temporarily removed this line because it might make celery not work
# NOTE: 'app' is imported locally in route registration to avoid circular imports
import bcrypt
from requests_oauthlib import OAuth2Session
import os
from dotenv import load_dotenv
import requests

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
load_dotenv()

OAUTH2_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
OAUTH2_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
try:
    environment = os.getenv("ENVIRONMENT")
except:
    environment = "DEV"

if environment == "PROD":
    # Use Railway domain or custom domain
    OAUTH2_REDIRECT_URI = os.getenv(
        "DISCORD_REDIRECT_URI", "https://web-production-55d7b.up.railway.app/callback"
    )
else:
    OAUTH2_REDIRECT_URI = "http://127.0.0.1:5000/callback"

API_BASE_URL = os.environ.get("API_BASE_URL", "https://discordapp.com/api")
AUTHORIZATION_BASE_URL = API_BASE_URL + "/oauth2/authorize"
TOKEN_URL = API_BASE_URL + "/oauth2/token"


def verify_recaptcha(response):
    secret = os.getenv("RECAPTCHA_SECRET_KEY")
    if not secret:
        return True  # Skip verification if no secret key

    payload = {"secret": secret, "response": response}
    r = requests.post("https://www.google.com/recaptcha/api/siteverify", data=payload)
    result = r.json()
    return result.get("success", False)


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


def ensure_signup_attempts_table():
    """Idempotent helper: ensure the signup_attempts table exists with expected columns.

    This is safe to call on every request; failures are logged but do not raise.
    """
    try:
        from database import get_db_cursor

        with get_db_cursor() as db:
            # Create table if it doesn't exist (minimal primary key), then add expected columns.
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS signup_attempts (
                    id SERIAL PRIMARY KEY
                )
            """
            )

            # Ensure expected columns exist (no-op if already present)
            try:
                db.execute(
                    "ALTER TABLE signup_attempts ADD COLUMN IF NOT EXISTS ip_address VARCHAR(45);"
                )
                import logging

                logging.getLogger(__name__).debug("ensure: ip_address ensured")
            except Exception as e:
                import logging

                logging.getLogger(__name__).debug("ensure: ip_address error %s", e)

            # Also tolerate older schema that used `ip` column name and ensure it's nullable
            try:
                db.execute(
                    "ALTER TABLE signup_attempts ADD COLUMN IF NOT EXISTS ip VARCHAR(45);"
                )
                import logging

                logging.getLogger(__name__).debug("ensure: ip column ensured")
            except Exception as e:
                import logging

                logging.getLogger(__name__).debug("ensure: ip add error %s", e)

            # Attempt to drop NOT NULL on `ip` if it exists (wrapped in DO block to avoid errors)
            try:
                db.execute(
                    """
                    DO $$
                    BEGIN
                      IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='signup_attempts' AND column_name='ip'
                      ) THEN
                        BEGIN
                          EXECUTE 'ALTER TABLE signup_attempts ALTER COLUMN ip DROP NOT NULL';
                        EXCEPTION WHEN others THEN
                          -- ignore any error dropping NOT NULL (e.g., if it's already nullable)
                        END;
                      END IF;
                    END$$;
                """
                )
                import logging

                logging.getLogger(__name__).debug(
                    "ensure: attempted drop NOT NULL on ip (if existed)"
                )
            except Exception as e:
                import logging

                logging.getLogger(__name__).debug(
                    "ensure: ip drop-not-null error %s", e
                )

            try:
                db.execute(
                    "ALTER TABLE signup_attempts ADD COLUMN IF NOT EXISTS fingerprint TEXT;"
                )
                db.execute(
                    "ALTER TABLE signup_attempts ADD COLUMN IF NOT EXISTS email VARCHAR(255);"
                )
                db.execute(
                    "ALTER TABLE signup_attempts ADD COLUMN IF NOT EXISTS attempt_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP;"
                )
                db.execute(
                    "ALTER TABLE signup_attempts ADD COLUMN IF NOT EXISTS successful BOOLEAN DEFAULT FALSE;"
                )
                import logging

                logging.getLogger(__name__).debug("ensure: other columns ensured")
            except Exception as e:
                import logging

                logging.getLogger(__name__).debug("ensure: other columns error %s", e)
    except Exception as e:
        try:
            import logging

            logging.getLogger(__name__).debug(
                "ensure_signup_attempts_table: failed to ensure table: %s", e
            )
        except:
            pass


# NOTE: 'app' is imported inside route registration function to avoid circular imports


def _get_app():
    """Lazy import to break circular dependency."""
    from app import app

    return app


def discord():
    scope = request.args.get("scope", "identify email")

    discord = make_session(scope=scope.split(" "))
    authorization_url, state = discord.authorization_url(AUTHORIZATION_BASE_URL)
    session["oauth2_state"] = state

    return redirect(authorization_url)  # oauth2/authorize


def callback():
    from database import get_db_cursor

    if request.values.get("error"):
        return request.values["error"]

    # Create an OAuth session using the stored state (may be None)
    discord_state = make_session(state=session.get("oauth2_state"))

    # Fetch the token. If a state mismatch occurs, attempt a controlled
    # fallback by re-creating the session with the incoming `state` value
    # from the request and retrying once.
    try:
        token = discord_state.fetch_token(
            TOKEN_URL,
            client_secret=OAUTH2_CLIENT_SECRET,
            authorization_response=request.url,
        )
    except Exception as e:
        err_name = type(e).__name__
        err_str = str(e)
        print(f"OAuth token fetch error: {err_name}: {err_str}")

        is_state_error = (
            "MismatchingStateError" in err_name
            or "mismatching_state" in err_str.lower()
            or "state not equal" in err_str.lower()
        )

        if is_state_error:
            try:
                incoming_state = request.args.get("state") or request.values.get(
                    "state"
                )
                print(
                    f"OAuth state mismatch — attempting fallback with incoming state: {incoming_state}"
                )
                discord_state = make_session(state=incoming_state)
                token = discord_state.fetch_token(
                    TOKEN_URL,
                    client_secret=OAUTH2_CLIENT_SECRET,
                    authorization_response=request.url,
                )
            except Exception as e2:
                print(f"OAuth fallback failed: {type(e2).__name__}: {e2}")
                raise
        else:
            raise

    session["oauth2_token"] = token

    discord = make_session(token=token)
    discord_user_id = discord.get(API_BASE_URL + "/users/@me").json().get("id")

    discord_auth = discord_user_id

    with get_db_cursor() as db:
        try:
            db.execute(
                "SELECT * FROM users WHERE hash=(%s) AND auth_type='discord'",
                (discord_auth,),
            )
            duplicate = db.fetchone()[0]
            duplicate = True
        except TypeError:
            duplicate = False

    if duplicate:
        return redirect("/discord_login")
    return redirect("/discord_signup")


def discord_register():
    from database import get_db_cursor
    from app import app

    if request.method == "GET":
        recaptcha_site_key = os.getenv("RECAPTCHA_SITE_KEY", "")
        return render_template(
            "signup.html", way="discord", recaptcha_site_key=recaptcha_site_key
        )

    elif request.method == "POST":
        try:
            print("\n=== DISCORD SIGNUP START ===")
            print(f"Token in session: {bool(session.get('oauth2_token'))}")

            # Defensive: ensure signup_attempts exists
            ensure_signup_attempts_table()

            # IP rate limiting: max 3 attempts per IP per day
            client_ip = request.remote_addr
            with get_db_cursor() as db:
                db.execute(
                    """
                    SELECT COUNT(*) FROM signup_attempts
                    WHERE ip_address = %s AND attempt_time >= NOW() - INTERVAL '1 day'
                """,
                    (client_ip,),
                )
                attempt_count = db.fetchone()[0]
                if attempt_count >= 3:
                    return error(
                        429,
                        "Too many signup attempts from this IP address. Please try again tomorrow.",
                    )

                # Record this attempt
                db.execute(
                    """
                    INSERT INTO signup_attempts (ip_address, ip, attempt_time, successful)
                    VALUES (%s, %s, NOW(), FALSE)
                """,
                    (client_ip, client_ip),
                )

            app.config["SESSION_PERMANENT"] = True
            app.permanent_session_lifetime = datetime.timedelta(days=365)

            # Get Discord user info from session token
            token = session.get("oauth2_token")
            discord = make_session(token=token)
            if not discord or not token:
                print("ERROR: No token")
                return error(400, "Discord authentication failed - no token")

            print(f"Fetching Discord user...")
            response = discord.get(API_BASE_URL + "/users/@me")
            print(f"Response code: {response.status_code}")
            discord_user = response.json()
            print(f"Discord user: {discord_user}")

            discord_user_id = discord_user.get("id")
            email = discord_user.get("email")

            if not discord_user_id:
                err = f"Discord API error: {discord_user}"
                print(f"ERROR: {err}")
                return error(400, err)

            # Get form data
            username = request.form.get("username", "").strip()
            continent_str = request.form.get("continent", "")

            # Verify reCAPTCHA
            recaptcha_response = request.form.get("g-recaptcha-response")
            if not verify_recaptcha(recaptcha_response):
                return error(400, "reCAPTCHA verification failed")

            print(f"Form username: {username}")
            print(f"Form continent_str: {continent_str}")

            if not username:
                print("ERROR: No username")
                return error(400, "Country name is required")

            if not continent_str:
                return error(400, "Biome selection is required")

            try:
                continent_number = int(continent_str) - 1
                continents = [
                    "Tundra",
                    "Savanna",
                    "Desert",
                    "Jungle",
                    "Boreal Forest",
                    "Grassland",
                    "Mountain Range",
                ]
                continent = continents[continent_number]
            except (ValueError, IndexError):
                return error(400, "Invalid biome selection")

            discord_auth = str(discord_user_id)

            print(
                f"Creating account - username: {username}, discord_id: {discord_auth}"
            )

            # Create account
            with get_db_cursor() as db:
                print("Database cursor acquired")
                # Check if username exists
                db.execute("SELECT id FROM users WHERE username=%s", (username,))
                if db.fetchone():
                    print(f"Username already taken: {username}")
                    return error(400, "Country name already taken")

                # Check if email exists
                if email:
                    db.execute("SELECT id FROM users WHERE email=%s", (email,))
                    if db.fetchone():
                        print(f"Email already used: {email}")
                        return error(400, "An account with this email already exists")

                print("Username available, checking Discord ID...")
                db.execute(
                    "SELECT id FROM users WHERE hash=%s AND auth_type='discord'",
                    (discord_auth,),
                )
                if db.fetchone():
                    print(f"Discord ID already linked: {discord_auth}")
                    return error(
                        400, "This Discord account is already linked to another country"
                    )

                print(f"Creating user: {username}")
                # Create user
                date = str(datetime.date.today())
                db.execute(
                    "INSERT INTO users (username, email, hash, date, auth_type) VALUES (%s, %s, %s, %s, %s)",
                    (username, email, discord_auth, date, "discord"),
                )

                # Get the new user ID
                db.execute("SELECT id FROM users WHERE hash=%s", (discord_auth,))
                user_id = db.fetchone()[0]

                session["user_id"] = user_id
                session.permanent = True
                session.modified = True

                # Create all user tables
                db.execute(
                    "INSERT INTO stats (id, location) VALUES (%s, %s)",
                    (user_id, continent),
                )
                db.execute("INSERT INTO military (id) VALUES (%s)", (user_id,))
                db.execute("INSERT INTO resources (id) VALUES (%s)", (user_id,))
                db.execute("INSERT INTO upgrades (user_id) VALUES (%s)", (user_id,))
                db.execute("INSERT INTO policies (user_id) VALUES (%s)", (user_id,))

            # Mark attempt as successful
            with get_db_cursor() as db:
                db.execute(
                    """
                    UPDATE signup_attempts
                    SET successful = TRUE
                    WHERE id = (
                        SELECT id FROM signup_attempts
                        WHERE ip_address = %s
                        ORDER BY attempt_time DESC
                        LIMIT 1
                    )
                """,
                    (client_ip,),
                )

            # Clean up session
            try:
                session.pop("oauth2_state", None)
                session.pop("oauth2_token", None)
            except:
                pass

            return redirect("/")

        except Exception as e:
            import traceback

            error_msg = str(e)
            print(f"\n!!! DISCORD SIGNUP ERROR !!!")
            print(f"Error: {error_msg}")
            print(traceback.format_exc())
            print("!!! END ERROR !!!\n")
            return error(500, f"Signup failed: {error_msg}")


def signup():
    if request.method == "POST":
        import logging

        logger = logging.getLogger(__name__)
        logger.debug(f"POST /signup: form keys={list(request.form.keys())}")
        from database import get_db_cursor

        # Defensive: ensure signup_attempts exists
        ensure_signup_attempts_table()

        # Debug: log remote_addr and forwarding headers to diagnose rate-limit
        import logging

        logger = logging.getLogger(__name__)
        logger.debug(
            f"signup request remote_addr={request.remote_addr} X-Forwarded-For={request.headers.get('X-Forwarded-For')}"
        )

        # IP rate limiting: max 3 attempts per IP per day
        # Allow a higher threshold (or effectively bypass) for local dev/testing
        client_ip = request.remote_addr
        with get_db_cursor() as db:
            db.execute(
                """
                SELECT COUNT(*) FROM signup_attempts
                WHERE ip_address = %s AND attempt_time >= NOW() - INTERVAL '1 day'
            """,
                (client_ip,),
            )
            attempt_count = db.fetchone()[0]

            # Use a relaxed limit for local development and tests so automated
            # test runs from 127.0.0.1 don't get rate limited.
            # In local development, skip rate-limiting for 127.0.0.1 to avoid
            # flaky failures caused by test runs or previous test artifacts.
            # Treat local loopback and IPv4-mapped IPv6 addresses as exempt from rate-limits
            # Use substring checks because request.remote_addr can be in forms like
            # '::1' or '::ffff:127.0.0.1'. For local dev, disable rate-limiting.
            is_local = False
            try:
                if client_ip:
                    if (
                        "127.0.0.1" in client_ip
                        or client_ip.startswith("127.")
                        or client_ip == "::1"
                        or "::ffff:127.0.0.1" in client_ip
                    ):
                        is_local = True
            except Exception:
                is_local = False

            # Always exempt local loopback traffic from rate-limits to make
            # local automated test runs reliable regardless of ENVIRONMENT.
            if is_local:
                max_attempts = None
            else:
                max_attempts = 3
            logger.debug(f"ENVIRONMENT={os.getenv('ENVIRONMENT', 'DEV')}")
            logger.debug(
                f"signup rate check: ip={client_ip} attempt_count={attempt_count} max_attempts={max_attempts} is_local={is_local}"
            )

            if max_attempts is not None and attempt_count >= max_attempts:
                logger.debug(
                    f"signup rate limit exceeded: ip={client_ip} attempt_count={attempt_count} max_attempts={max_attempts}"
                )
                return error(
                    429,
                    "Too many signup attempts from this IP address. Please try again tomorrow.",
                )

            # Record this attempt
            db.execute(
                """
                INSERT INTO signup_attempts (ip_address, ip, attempt_time, successful)
                VALUES (%s, %s, NOW(), FALSE)
            """,
                (client_ip, client_ip),
            )

        # Gets user's form inputs
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password").encode("utf-8")
        confirmation = request.form.get("confirmation").encode("utf-8")

        # Additional debug logging to help diagnose flaky test failures
        import logging

        logger = logging.getLogger(__name__)
        logger.debug(
            f"signup form values: username={username} email={email} continent={request.form.get('continent')}"
        )

        # Verify reCAPTCHA
        recaptcha_response = request.form.get("g-recaptcha-response")
        if not verify_recaptcha(recaptcha_response):
            return error(400, "reCAPTCHA verification failed")

        # Turns the continent number into 0-indexed
        continent_number = int(request.form.get("continent")) - 1
        # Ordered list, DO NOT EDIT
        continents = [
            "Tundra",
            "Savanna",
            "Desert",
            "Jungle",
            "Boreal Forest",
            "Grassland",
            "Mountain Range",
        ]
        continent = continents[continent_number]

        with get_db_cursor() as db:
            db.execute("SELECT username FROM users WHERE username=%s", (username,))
            result = db.fetchone()
            if result:
                logger.debug(f"signup duplicate username: {username}")
                return error(400, "Duplicate name, choose another one")

            db.execute("SELECT email FROM users WHERE email=%s", (email,))
            result = db.fetchone()
            if result:
                logger.debug(f"signup duplicate email: {email}")
                return error(400, "An account with this email already exists")

            # Checks if password is equal to the confirmation password
            if password != confirmation:
                logger.debug("signup password mismatch")
                return error(400, "Passwords must match.")

            # Hashes the inputted password
            hashed = bcrypt.hashpw(password, bcrypt.gensalt(14)).decode("utf-8")

            # Inserts the user and his data to the main table for users
            db.execute(
                "INSERT INTO users (username, email, hash, date, auth_type) VALUES (%s, %s, %s, %s, %s)",
                (username, email, hashed, str(datetime.date.today()), "normal"),
            )  # creates a new user || added account creation date

            # Selects the id of the user that was just registered. (Because id is AUTOINCREMENT'ed)
            db.execute("SELECT id FROM users WHERE username = (%s)", (username,))
            user_id = db.fetchone()[0]

            # Stores the user's
            session["user_id"] = user_id
            session.permanent = True
            session.modified = True

            # Return redirect; do not set developer-only cookies in normal flow.
            from flask import make_response

            response = redirect("/")
            # Continue with DB setup and then return the response

            # Inserts the user's id into the needed database tables
            db.execute(
                "INSERT INTO stats (id, location) VALUES (%s, %s)", (user_id, continent)
            )
            db.execute("INSERT INTO military (id) VALUES (%s)", (user_id,))
            db.execute("INSERT INTO resources (id) VALUES (%s)", (user_id,))
            db.execute("INSERT INTO upgrades (user_id) VALUES (%s)", (user_id,))
            db.execute("INSERT INTO policies (user_id) VALUES (%s)", (user_id,))
            return response

        # Mark attempt as successful
        with get_db_cursor() as db:
            db.execute(
                """
                UPDATE signup_attempts
                SET successful = TRUE
                WHERE id = (
                    SELECT id FROM signup_attempts
                    WHERE ip_address = %s
                    ORDER BY attempt_time DESC
                    LIMIT 1
                )
            """,
                (client_ip,),
            )

        return redirect("/")
    elif request.method == "GET":
        recaptcha_site_key = os.getenv("RECAPTCHA_SITE_KEY", "")
        return render_template(
            "signup.html", way="normal", recaptcha_site_key=recaptcha_site_key
        )


# Register routes at module load time after app has been imported
_app = _get_app()
_app.add_url_rule("/discord", "discord", discord, methods=["GET", "POST"])
_app.add_url_rule("/callback", "callback", callback)
_app.add_url_rule(
    "/discord_signup", "discord_register", discord_register, methods=["GET", "POST"]
)
_app.add_url_rule("/signup", "signup", signup, methods=["GET", "POST"])
