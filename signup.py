# FULLY MIGRATED
# flake8: max-line-length=200

from flask import request, render_template, session, redirect, flash
import datetime
from helpers import error
import logging

# Configure logger for signup
logger = logging.getLogger(__name__)

# Game.ping() # temporarily removed this line because it might make celery not work
# NOTE: 'app' is imported locally in route registration to avoid circular imports
import bcrypt  # noqa: E402
from requests_oauthlib import OAuth2Session  # noqa: E402
import os  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
import requests  # noqa: E402

load_dotenv()
if os.getenv("ENVIRONMENT") != "PROD" and not os.getenv("RAILWAY_ENVIRONMENT_NAME"):
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"


def _complete_referral_signup(db, user_id: int) -> None:
    """Link inviter from session/form and grant invitee signup bonus."""
    from app_core.referrals.service import (
        apply_signup_referral_bonus,
        link_referrer_on_signup,
        referral_code_from_signup_request,
    )

    code = referral_code_from_signup_request()
    link_referrer_on_signup(db, user_id, code)
    apply_signup_referral_bonus(db, user_id)
    try:
        session.pop("referral_code", None)
    except RuntimeError:
        pass


def _init_economy_tables(db, user_id):
    """Initialize Economy 2.0 normalized tables for a new player.

    Creates rows in user_economy (one per resource), user_buildings (one per
    building) and user_military (one per unit) with quantity 0.  Uses
    ON CONFLICT DO NOTHING so the call is idempotent.
    """
    # user_economy — one row per resource in resource_dictionary
    db.execute(
        "INSERT INTO user_economy (user_id, resource_id, quantity) "
        "SELECT %s, resource_id, 0 FROM resource_dictionary "
        "ON CONFLICT DO NOTHING",
        (user_id,),
    )

    # Starter care package — enough to build farm + coal plant + mine without market.
    starter_resources = [
        ("lumber", 120_000),
        ("iron", 50_000),
        ("coal", 50_000),
        ("rations", 350_000),
        ("steel", 15_000),
        ("components", 10_000),
        ("aluminium", 10_000),
    ]
    for res_name, qty in starter_resources:
        db.execute(
            """
            UPDATE user_economy SET quantity = quantity + %s
            WHERE user_id = %s
              AND resource_id = (
                  SELECT resource_id FROM resource_dictionary WHERE name = %s
              )
            """,
            (qty, user_id, res_name),
        )

    # user_buildings — rows are created per-province when buildings are
    # purchased (INSERT ON CONFLICT in action_loop.build_structure).
    # No need to pre-populate zero-quantity rows at signup.

    # user_military — one row per active unit in unit_dictionary
    db.execute(
        "INSERT INTO user_military (user_id, unit_id, quantity) "
        "SELECT %s, unit_id, 0 FROM unit_dictionary WHERE is_active = TRUE "
        "ON CONFLICT DO NOTHING",
        (user_id,),
    )
    logger.info("Economy 2.0 tables initialized for user_id=%s", user_id)

def init_user_game_data(db, user_id, continent):
    """Initialize all game-related data for a new user across all providers."""
    import logging
    logger = logging.getLogger(__name__)
    
    # 1. Stats
    db.execute(
        "INSERT INTO stats (id, location, gold) VALUES (%s, %s, %s) "
        "ON CONFLICT DO NOTHING",
        (user_id, continent, 80_000_000),
    )
    
    # 2. Policies
    db.execute(
        "INSERT INTO policies (user_id) VALUES (%s) ON CONFLICT DO NOTHING",
        (user_id,),
    )
    
    # 3. Economy 2.0
    _init_economy_tables(db, user_id)
    
    logger.info(f"Initialized game data for user_id={user_id} on continent={continent}")



OAUTH2_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
OAUTH2_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
environment = os.getenv("ENVIRONMENT", "DEV")

if environment == "PROD" or os.getenv("RAILWAY_ENVIRONMENT_NAME"):
    # Use Railway domain or custom domain
    OAUTH2_REDIRECT_URI = os.getenv(
        "DISCORD_REDIRECT_URI", "https://affairsandorder.com/callback"
    )
else:
    OAUTH2_REDIRECT_URI = "http://127.0.0.1:5000/callback"

API_BASE_URL = os.environ.get("API_BASE_URL", "https://discord.com/api")
AUTHORIZATION_BASE_URL = API_BASE_URL + "/oauth2/authorize"
TOKEN_URL = API_BASE_URL + "/oauth2/token"


def verify_recaptcha(response):
    # Allow tests and CI to skip real recaptcha validation via environment.
    # This keeps CI deterministic and avoids external network calls during tests.
    try:
        # Prefer explicit SKIP_RECAPTCHA or CI env flags first
        if (
            os.getenv("GITHUB_ACTIONS")
            or os.getenv("CI")
            or os.getenv("SKIP_RECAPTCHA")
        ):
            return True
        # If running under Flask test mode, bypass recaptcha as well
        from flask import current_app

        if getattr(current_app, "testing", False):
            return True
    except Exception:
        # If any import or check fails, fallthrough to normal behavior
        pass

    secret = os.getenv("RECAPTCHA_SECRET_KEY")
    if not secret:
        return True

    # If no response token was supplied, treat this as a failed verification
    # in production, but allow tests to pass if they explicitly skip recaptcha.
    if not response:
        return False

    payload = {"secret": secret, "response": response}
    try:
        r = requests.post(
            "https://www.google.com/recaptcha/api/siteverify",
            data=payload,
            timeout=3,
        )
        result = r.json()
        return result.get("success", False)
    except Exception as e:
        # If recaptcha verification fails due to network issues, log and
        # treat as failure (do not block indefinitely). In production we may
        # want to allow a configurable leniency, but default to safe failure.
        logger.warning("recaptcha verification failed: %s", e)
        return False


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



_signup_table_ensured = False


def ensure_signup_attempts_table():
    """Idempotent helper: ensure the signup_attempts table exists with expected columns.

    This is safe to call on every request; failures are logged but do not raise.
    DDL is only executed once per process lifetime.
    """
    global _signup_table_ensured
    if _signup_table_ensured:
        return
    try:
        from database import get_request_cursor

        with get_request_cursor() as db:
            # Create table if it doesn't exist (minimal primary key).
            # Afterwards, add expected columns.
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
                    "ALTER TABLE signup_attempts "
                    "ADD COLUMN IF NOT EXISTS ip_address VARCHAR(45);"
                )
                import logging

                logging.getLogger(__name__).debug("ensure: ip_address ensured")
            except Exception as e:
                import logging

                logging.getLogger(__name__).debug("ensure: ip_address error %s", e)

            # Also tolerate older schema that used `ip` column name.
            # Ensure it's nullable.
            try:
                db.execute(
                    "ALTER TABLE signup_attempts "
                    "ADD COLUMN IF NOT EXISTS ip VARCHAR(45);"
                )
                import logging

                logging.getLogger(__name__).debug("ensure: ip column ensured")
            except Exception as e:
                import logging

                logging.getLogger(__name__).debug("ensure: ip add error %s", e)

            # Attempt to drop NOT NULL on `ip` if it exists.
            # Use a simple ALTER inside try/except; if it fails, rollback the
            # transaction so subsequent ALTERs can proceed.
            try:
                db.execute("ALTER TABLE signup_attempts ALTER COLUMN ip DROP NOT NULL")
            except Exception as e:
                try:
                    db.connection.rollback()
                except Exception:
                    pass
                import logging

                logging.getLogger(__name__).debug(
                    "ensure: ip drop-not-null error %s", e
                )

            try:
                db.execute(
                    "ALTER TABLE signup_attempts "
                    "ADD COLUMN IF NOT EXISTS fingerprint TEXT;"
                )
                db.execute(
                    "ALTER TABLE signup_attempts "
                    "ADD COLUMN IF NOT EXISTS email VARCHAR(255);"
                )
                db.execute(
                    "ALTER TABLE signup_attempts "
                    "ADD COLUMN IF NOT EXISTS attempt_time "
                    "TIMESTAMP DEFAULT CURRENT_TIMESTAMP;"
                )
                db.execute(
                    "ALTER TABLE signup_attempts "
                    "ADD COLUMN IF NOT EXISTS successful BOOLEAN DEFAULT FALSE;"
                )
                import logging

                logging.getLogger(__name__).debug("ensure: other columns ensured")
            except Exception as e:
                import logging

                logging.getLogger(__name__).debug("ensure: other columns error %s", e)
        _signup_table_ensured = True
    except Exception as e:
        try:
            import logging

            logging.getLogger(__name__).debug(
                "ensure_signup_attempts_table: failed to ensure table: %s", e
            )
        except Exception:
            pass


# NOTE: 'app' is imported inside route registration function to avoid circular imports


def _get_app():
    """Lazy import to break circular dependency."""
    from app import app

    return app


def discord():
    scope = request.args.get("scope", "identify email")
    intent = request.args.get("intent", "login")

    discord = make_session(scope=scope.split(" "))
    authorization_url, state = discord.authorization_url(AUTHORIZATION_BASE_URL)
    session["oauth2_state"] = state
    session["oauth2_intent"] = intent

    return redirect(authorization_url)  # oauth2/authorize


def callback():
    from database import get_request_cursor

    if request.values.get("error"):
        return request.values["error"]

    # Create an OAuth session using the stored state (may be None)
    # Guard against missing oauth2_state in session
    oauth_state = session.get("oauth2_state")
    if not oauth_state and "state" in request.values:
        oauth_state = request.values["state"]

    if not OAUTH2_CLIENT_SECRET:
        import logging
        logging.getLogger(__name__).error("DISCORD_CLIENT_SECRET not set")
        return error(500, "Discord login misconfigured (missing client secret)")


    discord_state = make_session(state=oauth_state)

    # Fetch the token. If a state mismatch occurs, attempt a controlled
    # fallback by re-creating the session with the incoming `state` value
    # from the request and retrying once.
    try:
        auth_response = request.url
        environment = os.getenv("ENVIRONMENT", "DEV")
        if environment == "PROD" or os.getenv("RAILWAY_ENVIRONMENT_NAME"):
            if auth_response.startswith("http://"):
                auth_response = auth_response.replace("http://", "https://", 1)

        token = discord_state.fetch_token(
            TOKEN_URL,
            client_secret=OAUTH2_CLIENT_SECRET,
            authorization_response=auth_response,
        )
        session["oauth2_token"] = token

        discord = make_session(token=token)
        user_info = discord.get(API_BASE_URL + '/users/@me').json()
        discord_user_id = user_info['id']
        session['discord_email'] = user_info.get('email') if user_info.get('verified') else None

        intent = session.get('oauth2_intent', 'login')
        
        with get_request_cursor() as db:
            if intent == 'link':
                if 'user_id' not in session:
                    return error(401, "You must be logged in to link your Discord account.")
                from database import users_table_has_column, rollback_db_cursor

                if users_table_has_column("discord_id"):
                    from database import assign_discord_id_to_user

                    existing = None
                    db.execute(
                        "SELECT id FROM users WHERE discord_id=%s OR (hash=%s AND auth_type='discord') LIMIT 1",
                        (discord_user_id, discord_user_id),
                    )
                    row = db.fetchone()
                    if row:
                        existing = row[0]
                    if existing is not None and existing != session["user_id"]:
                        rollback_db_cursor(db)
                        return error(
                            400,
                            "This Discord account is already linked to another nation.",
                        )
                    assign_discord_id_to_user(session["user_id"], discord_user_id)
                else:
                    rollback_db_cursor(db)
                session.pop('oauth2_intent', None)
                return redirect("/account")
                
            elif intent == 'reset':
                from database import users_table_has_column, rollback_db_cursor

                if users_table_has_column("discord_id"):
                    db.execute(
                        "SELECT id FROM users WHERE discord_id=%s OR (hash=%s AND auth_type='discord') LIMIT 1",
                        (discord_user_id, discord_user_id),
                    )
                else:
                    db.execute(
                        "SELECT id FROM users WHERE hash=%s AND auth_type='discord' LIMIT 1",
                        (discord_user_id,),
                    )
                user = db.fetchone()
                if user:
                    session['reset_user_id'] = user[0]
                    session.pop('oauth2_intent', None)
                    return redirect("/discord_reset_password_page")
                else:
                    flash(
                        "No account linked to this Discord ID was found. "
                        "Use your backup recovery key or contact support to relink Discord."
                    )
                    session.pop('oauth2_intent', None)
                    return redirect("/forgot_password")

            from database import users_table_has_column

            if users_table_has_column("discord_id"):
                db.execute(
                    "SELECT 1 FROM users WHERE (hash=%s AND auth_type='discord') OR discord_id=%s LIMIT 1",
                    (discord_user_id, discord_user_id),
                )
            else:
                db.execute(
                    "SELECT 1 FROM users WHERE hash=%s AND auth_type='discord' LIMIT 1",
                    (discord_user_id,),
                )
            duplicate = db.fetchone() is not None

        if duplicate:
            return redirect("/discord_login/")

        discord_email = (session.get("discord_email") or "").strip()
        if discord_email:
            from database import assign_discord_id_to_user

            with get_request_cursor() as link_db:
                link_db.execute(
                    """
                    SELECT id, discord_id
                    FROM users
                    WHERE LOWER(email) = LOWER(%s)
                    LIMIT 1
                    """,
                    (discord_email,),
                )
                email_row = link_db.fetchone()
            if email_row:
                linked_user_id, existing_discord = email_row[0], email_row[1]
                if (
                    existing_discord
                    and str(existing_discord) != str(discord_user_id)
                ):
                    flash(
                        "This email is already linked to a different Discord account. "
                        "Log in with email/password or contact support."
                    )
                    return redirect("/login?discord_error=email_conflict")
                assign_discord_id_to_user(linked_user_id, discord_user_id)
                return redirect("/discord_login/")

        return redirect("/discord_signup")
    except Exception as e:
        err_name = type(e).__name__
        err_str = str(e)
        logger.warning(f"OAuth token fetch error: {err_name}: {err_str}")

        is_state_error = (
            "MismatchingStateError" in err_name
            or "mismatching_state" in err_str.lower()
            or "state not equal" in err_str.lower()
        )

        if is_state_error:
            logger.warning("OAuth state mismatch — rejecting login (no fallback)")
        return redirect("/login?discord_error=session")


def discord_register():
    from database import get_request_cursor
    from app import app

    if request.method == "GET":
        from app_core.referrals.service import capture_referral_from_request

        referral_invite = capture_referral_from_request()
        recaptcha_site_key = os.getenv("RECAPTCHA_SITE_KEY", "")
        return render_template(
            "signup.html",
            way="discord",
            recaptcha_site_key=recaptcha_site_key,
            referral_invite=referral_invite,
        )

    elif request.method == "POST":
        try:
            logger.debug("Discord signup started")

            # Defensive: ensure signup_attempts exists
            ensure_signup_attempts_table()

            # IP rate limiting: max 3 attempts per IP per day
            # Prefer X-Forwarded-For when present (app may run behind a proxy)
            forwarded = request.headers.get("X-Forwarded-For") or request.headers.get(
                "X-Forwarded-For".lower()
            )
            if forwarded:
                # Use first IP in list if Multiple forwarded addresses are present
                client_ip = forwarded.split(",")[0].strip()
            else:
                client_ip = request.remote_addr

            with get_request_cursor() as db:
                db.execute(
                    """
                    SELECT COUNT(*) FROM signup_attempts
                    WHERE ip_address = %s AND attempt_time >= NOW() - INTERVAL '1 day'
                """,
                    (client_ip,),
                )
                attempt_row = db.fetchone()
                attempt_count = attempt_row[0] if attempt_row else 0
                if attempt_count >= 10:
                    return error(
                        429,
                        "Too many signup attempts from this IP."
                        " Please try again tomorrow.",
                    )

                # Record this attempt
                db.execute(
                    """
                    INSERT INTO signup_attempts (
                        ip_address, ip, attempt_time, successful
                    )
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
                logger.warning("Discord signup failed - no token in session")
                return error(400, "Discord authentication failed - no token")

            try:
                response = discord.get(API_BASE_URL + "/users/@me", timeout=3)
                discord_user = response.json()
            except Exception as e:
                logger.error("Discord API user fetch failed: %s", e)
                return error(400, "Discord API error: failed to fetch user info")

            discord_user_id = discord_user.get("id")
            email = discord_user.get("email") if discord_user.get("verified") else None

            if not discord_user_id:
                err = f"Discord API error: {discord_user}"
                logger.error(err)
                return error(400, err)

            # Get form data
            username = request.form.get("username", "").strip()
            continent_str = request.form.get("continent", "")

            # Verify reCAPTCHA
            recaptcha_response = request.form.get("g-recaptcha-response")
            if not verify_recaptcha(recaptcha_response):
                return error(400, "reCAPTCHA verification failed")

            if not username:
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

            logger.info(f"Creating account: {username}")

            # Create account
            with get_request_cursor() as db:
                # Check if username exists
                db.execute("SELECT id FROM users WHERE username=%s", (username,))
                if db.fetchone():
                    return error(400, "Country name already taken")

                # Check if email exists
                if email:
                    db.execute("SELECT id FROM users WHERE email=%s", (email,))
                    if db.fetchone():
                        return error(400, "An account with this email already exists")

                from database import users_table_has_column
                if users_table_has_column("discord_id"):
                    db.execute(
                        "SELECT id FROM users WHERE discord_id=%s OR (hash=%s AND auth_type='discord')",
                        (discord_auth, discord_auth),
                    )
                else:
                    db.execute(
                        "SELECT id FROM users WHERE hash=%s AND auth_type='discord'",
                        (discord_auth,),
                    )
                if db.fetchone():
                    return error(
                        400, "This Discord account is already linked to another country"
                    )

                # Create user
                # Discord users are auto-verified since Discord verifies emails
                date = str(datetime.date.today())
                db.execute(
                    "INSERT INTO users (username, email, hash, date, "
                    "auth_type, is_verified) VALUES (%s, %s, %s, %s, %s, %s)",
                    (username, email, discord_auth, date, "discord", True),
                )

                # Get the new user ID
                db.execute("SELECT id FROM users WHERE hash=%s", (discord_auth,))
                discord_user_row = db.fetchone()
                if not discord_user_row:
                    return error(500, "Signup failed: could not create user")
                user_id = discord_user_row[0]

                session["user_id"] = user_id
                session.permanent = True
                session.modified = True

                # Create all user tables (idempotent)
                # NOTE: resources and upgrades tables were removed in Economy 2.0
                # migration; their data now lives in user_economy / user_buildings.
                db.execute(
                    "INSERT INTO stats (id, location, gold) VALUES (%s, %s, %s) "
                    "ON CONFLICT DO NOTHING",
                    (user_id, continent, 80_000_000),
                )
                db.execute(
                    "INSERT INTO policies (user_id) VALUES (%s) ON CONFLICT DO NOTHING",
                    (user_id,),
                )

                # Initialize Economy 2.0 normalized tables
                _init_economy_tables(db, user_id)
                _complete_referral_signup(db, user_id)

            # Mark attempt as successful
            with get_request_cursor() as db:
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
            except (KeyError, RuntimeError):
                pass

            from app_core.onboarding.service import post_signup_redirect

            return redirect(post_signup_redirect(user_id))

        except Exception as e:
            error_msg = str(e)
            logger.exception(f"Discord signup error: {error_msg}")
            return error(500, f"Signup failed: {error_msg}")


def signup():
    if request.method == "POST":
        from database import get_request_cursor

        # Defensive: ensure signup_attempts exists
        ensure_signup_attempts_table()

        from helpers import client_ip_from_request

        client_ip = client_ip_from_request()
        logger.debug(
            "signup request remote_addr=%s client_ip=%s",
            request.remote_addr,
            client_ip,
        )

        # Allow a higher threshold (or effectively bypass) for local dev/testing
        with get_request_cursor() as db:
            db.execute(
                """
                SELECT COUNT(*) FROM signup_attempts
                WHERE ip_address = %s AND attempt_time >= NOW() - INTERVAL '1 day'
            """,
                (client_ip,),
            )
            attempt_row = db.fetchone()
            attempt_count = attempt_row[0] if attempt_row else 0

            # Use a relaxed limit for local development and tests so automated
            # test runs from 127.0.0.1 don't get rate limited.
            # In local development, skip rate-limiting for 127.0.0.1 to avoid
            # flaky failures caused by test runs or previous test artifacts.
            # Treat local loopback and IPv4-mapped IPv6 addresses
            # as exempt from rate-limits
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
                max_attempts = 10
            logger.debug(f"ENVIRONMENT={os.getenv('ENVIRONMENT', 'DEV')}")
            logger.debug(
                "signup rate check: ip=%s attempt_count=%s max_attempts=%s is_local=%s",
                client_ip,
                attempt_count,
                max_attempts,
                is_local,
            )

            if max_attempts is not None and attempt_count >= max_attempts:
                logger.debug(
                    "signup rate limit exceeded: ip=%s attempt_count=%s "
                    "max_attempts=%s",
                    client_ip,
                    attempt_count,
                    max_attempts,
                )
                return error(
                    429,
                    "Too many signup attempts from this IP."
                    " Please try again tomorrow.",
                )

            # Record this attempt
            db.execute(
                """
                INSERT INTO signup_attempts (ip_address, ip, attempt_time, successful)
                VALUES (COALESCE(%s, 'unknown'), COALESCE(%s, 'unknown'), NOW(), FALSE)
            """,
                (client_ip, client_ip),
            )

        # Gets user's form inputs
        username = request.form.get("username")
        email = request.form.get("email")
        password_raw = request.form.get("password")
        confirmation_raw = request.form.get("confirmation")
        if not password_raw or not confirmation_raw:
            return error(400, "Password and confirmation are required")
        password = password_raw.encode("utf-8")
        confirmation = confirmation_raw.encode("utf-8")

        # Additional debug logging to help diagnose flaky test failures
        logger.debug(
            "signup form values: username=%s email=%s continent=%s",
            username,
            email,
            request.form.get("continent"),
        )

        # Verify reCAPTCHA
        recaptcha_response = request.form.get("g-recaptcha-response")
        if not verify_recaptcha(recaptcha_response):
            return error(400, "reCAPTCHA verification failed")

        # Turns the continent number into 0-indexed
        continent_str = request.form.get("continent")
        if not continent_str:
            return error(400, "Continent selection is required")
        try:
            continent_number = int(continent_str) - 1
        except (ValueError, TypeError):
            return error(400, "Continent must be a valid number")

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

        if continent_number < 0 or continent_number >= len(continents):
            return error(400, "Invalid continent selection")

        continent = continents[continent_number]

        with get_request_cursor() as db:
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
            hashed = bcrypt.hashpw(password, bcrypt.gensalt(12)).decode("utf-8")

            # Check if email verification columns exist
            from email_utils import (
                generate_verification_token,
                send_verification_email,
                is_email_configured,
            )

            try:
                # Try to use email verification if columns exist
                db.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'users' AND column_name = 'verification_token'"
                )
                has_verification = db.fetchone() is not None
            except Exception:
                has_verification = False

            if has_verification and is_email_configured():
                # New flow with email verification
                verification_token = generate_verification_token(email)
                db.execute(
                    "INSERT INTO users (username, email, hash, date, "
                    "auth_type, is_verified, verification_token, token_created_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())",
                    (
                        username,
                        email,
                        hashed,
                        str(datetime.date.today()),
                        "normal",
                        False,
                        verification_token,
                    ),
                )
            else:
                # Legacy flow without email verification
                db.execute(
                    "INSERT INTO users (username, email, hash, date, "
                    "auth_type, is_verified) VALUES (%s, %s, %s, %s, %s, %s)",
                    (username, email, hashed, str(datetime.date.today()), "normal", True),
                )
                verification_token = None

            # Selects the id of the user that was just registered.
            # (Because id is AUTO-INCREMENT'ed)
            db.execute("SELECT id FROM users WHERE username = (%s)", (username,))
            new_user_row = db.fetchone()
            if not new_user_row:
                return error(500, "Signup failed: could not create user")
            user_id = new_user_row[0]

            # Send verification email if configured
            if verification_token and is_email_configured():
                email_sent = send_verification_email(
                    email, username, verification_token
                )
                if not email_sent:
                    logger.warning(f"Failed to send verification email to {email}")

            # Create all the user's game tables (idempotent)
            # Use ON CONFLICT DO NOTHING to tolerate duplicate inserts
            # (e.g. retries or concurrent/duplicate requests)
            # These must be created for ALL signup paths (verification and legacy)
            # NOTE: resources and upgrades tables were removed in Economy 2.0
            # migration; their data now lives in user_economy / user_buildings.
            init_user_game_data(db, user_id, continent)
            _complete_referral_signup(db, user_id)

            # Mark attempt as successful
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

            # If verification is enabled, redirect to pending page.
            # Otherwise, log them in and issue a one-time recovery key.
            if verification_token:
                import urllib.parse
                safe_email = urllib.parse.quote(email)
                return redirect(f"/verification_pending?email={safe_email}")
            else:
                from change import create_recovery_key_for_user

                session["user_id"] = user_id
                raw_key = create_recovery_key_for_user(db, user_id)
                from app_core.onboarding.service import post_signup_redirect

                if raw_key:
                    session["pending_recovery_key"] = raw_key
                    return redirect("/save_recovery_key")
                return redirect(post_signup_redirect(user_id))
    elif request.method == "GET":
        from app_core.referrals.service import capture_referral_from_request

        referral_invite = capture_referral_from_request()
        recaptcha_site_key = os.getenv("RECAPTCHA_SITE_KEY", "")
        return render_template(
            "signup.html",
            way="normal",
            recaptcha_site_key=recaptcha_site_key,
            referral_invite=referral_invite,
        )


def verification_pending():
    """Show the verification pending page after signup."""
    email = request.args.get("email", "")
    return render_template("verification_pending.html", email=email)


def save_recovery_key():
    """Show the one-time backup recovery key after signup or email verification."""
    raw_key = session.pop("pending_recovery_key", None)
    if not raw_key:
        if session.get("user_id"):
            return redirect("/")
        return redirect("/login")
    logged_in = bool(session.get("user_id"))
    return render_template(
        "save_recovery_key.html",
        recovery_key=raw_key,
        logged_in=logged_in,
    )


def verify_email():
    """Verify user's email address using the token from the email link."""
    from database import get_request_cursor
    from email_utils import verify_email_token

    token = request.args.get("token")
    if not token:
        return error(400, "Invalid verification link. No token provided.")

    # Verify the token
    email = verify_email_token(token)
    if not email:
        return error(
            400, "Invalid or expired verification link. Please request a new one."
        )

    try:
        with get_request_cursor() as cur:
            # Check if user exists and is not already verified
            cur.execute(
                """
                SELECT id, is_verified FROM users WHERE email = %s FOR UPDATE
            """,
                (email,),
            )
            result = cur.fetchone()

            if not result:
                return error(404, "User not found.")

            user_id, is_verified = result

            if is_verified:
                return redirect("/login?message=already_verified")

            # Mark user as verified
            cur.execute(
                """
                UPDATE users
                SET is_verified = TRUE, verification_token = NULL
                WHERE id = %s
            """,
                (user_id,),
            )

            from change import create_recovery_key_for_user

            session["user_id"] = user_id
            raw_key = create_recovery_key_for_user(cur, user_id)
            if raw_key:
                session["pending_recovery_key"] = raw_key
                return redirect("/save_recovery_key")

            return redirect("/login?message=verified")
    except Exception as e:
        logger.error(f"Email verification error: {e}")
        return error(500, "An error occurred during verification. Please try again.")


def resend_verification():
    """Resend verification email."""
    from database import get_request_cursor
    from email_utils import generate_verification_token, send_verification_email

    if request.method != "POST":
        return redirect("/login")

    email = request.form.get("email", "").strip().lower()
    if not email:
        return error(400, "Please provide your email address.")

    try:
        with get_request_cursor() as cur:
            # Check if user exists and is not verified
            cur.execute(
                """
                SELECT id, username, is_verified FROM users WHERE email = %s
            """,
                (email,),
            )
            result = cur.fetchone()

            if not result:
                # Don't reveal if email exists
                return render_template(
                    "verification_pending.html",
                    email=email,
                    message=(
                        "If an account exists with this email, "
                        "a verification link has been sent."
                    ),
                )

            user_id, username, is_verified = result

            if is_verified:
                return redirect("/login?message=already_verified")

            # Generate new token and send email
            new_token = generate_verification_token(email)
            cur.execute(
                """
                UPDATE users
                SET verification_token = %s, token_created_at = NOW()
                WHERE id = %s
            """,
                (new_token, user_id),
            )

            send_verification_email(email, username, new_token)

            return render_template(
                "verification_pending.html",
                email=email,
                message="Verification email sent! Please check your inbox.",
            )
    except Exception as e:
        logger.error(f"Resend verification error: {e}")
        return error(500, "An error occurred. Please try again.")


def register_signup_routes(app_instance):
    """Register signup routes.
    This should be called by app.py AFTER app is fully initialized.
    """
    app_instance.add_url_rule("/discord", "discord", discord, methods=["GET", "POST"])
    app_instance.add_url_rule("/callback", "callback", callback)
    app_instance.add_url_rule(
        "/discord_signup", "discord_register", discord_register, methods=["GET", "POST"]
    )
    app_instance.add_url_rule("/signup", "signup", signup, methods=["GET", "POST"])
    # Email verification routes
    app_instance.add_url_rule(
        "/verification_pending", "verification_pending", verification_pending
    )
    app_instance.add_url_rule(
        "/save_recovery_key", "save_recovery_key", save_recovery_key, methods=["GET"]
    )
    app_instance.add_url_rule("/verify", "verify_email", verify_email)
    app_instance.add_url_rule(
        "/resend_verification",
        "resend_verification",
        resend_verification,
        methods=["POST"],
    )
