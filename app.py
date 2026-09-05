import ast
import sys
import os
import json
import hmac
import time as time_module
from flask import Flask, request, render_template, session, redirect, send_from_directory
from flask_compress import Compress
import traceback
from extensions import limiter

# Root modules
from app_core.upgrades.routes import bp as upgrades_bp
from app_core import intelligence
import change
import countries
import signup
import login

from wars.routes import wars_bp
from app_core.treaties import bp as treaties_bp
from app_core import policies
import statistics
import requests
from app_core.trade_agreements import register_trade_agreement_routes
import logging
from variables import MILDICT, PROVINCE_UNIT_PRICES
from flaskext.markdown import Markdown
from psycopg2.extras import RealDictCursor
from datetime import datetime as dt
import string
import random
from helpers import login_required, error
from database import (
    get_db_connection,
    get_db_cursor,
    get_request_cursor,
    query_cache,
    rollback_db_cursor,
    teardown_request_connection,
)
import province
import game_ui
import bot_api
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(-1, os.path.dirname(os.path.abspath(__file__)))
if not hasattr(ast, "Str"): ast.Str = ast.Constant
if not hasattr(ast, "Num"): ast.Num = ast.Constant
if not hasattr(ast, "NameConstant"): ast.NameConstant = ast.Constant
if not hasattr(ast, "Ellipsis"): ast.Ellipsis = ast.Constant

from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

def create_app():
    global app
    app.url_map.strict_slashes = False

    try:
        from database import ensure_schema_compat
        ensure_schema_compat()
    except Exception:
        pass


    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
        sentry_dsn = os.getenv("SENTRY_DSN")
        if sentry_dsn:
            sentry_sdk.init(
                dsn=sentry_dsn,
                integrations=[FlaskIntegration()],
                traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.0")),
                environment=os.getenv("ENVIRONMENT", "DEV"),
            )
    except Exception:
        pass

    @app.errorhandler(403)
    def forbidden_error(error_msg):
        logger = logging.getLogger(__name__)
        logger.warning(f"403 error handler triggered: {error_msg}")
        return render_template("error.html", code=403, message="You don't have permission to access this page."), 403

    @app.errorhandler(404)
    def not_found_error(error_msg):
        return render_template("error.html", code=404, message="Page not found."), 404

    @app.errorhandler(Exception)
    def handle_exception(e):
        import traceback
        import logging
        from werkzeug.exceptions import HTTPException
        logger = logging.getLogger(__name__)
        # Pass HTTP exceptions (404, 403, etc.) through to their proper handlers
        # instead of wrapping them as 500s with a raw traceback.
        if isinstance(e, HTTPException):
            return e
        logger.exception("Unhandled exception:")
        try:
            import sentry_sdk
            sentry_sdk.capture_exception(e)
        except Exception:
            pass
        return render_template("error.html", code=500, message="An unexpected error occurred. Please try again."), 500

    app.config["PREFERRED_URL_SCHEME"] = "https"
    app.config["SERVER_NAME"] = None
    app.config["ALLOWED_HOSTS"] = ["affairsandorder.com", "www.affairsandorder.com", "web-production-55d7b.up.railway.app"]
    app.config["SESSION_COOKIE_DOMAIN"] = None
    is_prod = (os.getenv("ENVIRONMENT") == "PROD" and os.getenv("RAILWAY_ENVIRONMENT_NAME") is not None)
    app.config["SESSION_COOKIE_SECURE"] = is_prod
    default_samesite = "None" if is_prod else "Lax"
    app.config["SESSION_COOKIE_SAMESITE"] = os.getenv("SESSION_COOKIE_SAMESITE", default_samesite)

    @app.before_request
    def before_request():
        from time import time
        request.start_time = time()
        try:
            import sentry_sdk
            user_id = session.get("user_id") if hasattr(session, "get") else None
            if user_id: sentry_sdk.set_user({"id": str(user_id)})
            else: sentry_sdk.set_user(None)
        except Exception:
            pass

        if request.host:
            host_only = request.host.split(":")[0].lower()
            port = request.host.split(":", 1)[1] if ":" in request.host else ""
            canonical_host = None
            if host_only.startswith("www."):
                canonical_host = host_only[4:]
            # .com exists only as a redirect to .org (the primary domain).
            # OAuth (Discord/Google) redirect URIs now point at .org directly —
            # they used to be registered on .com, which required this whole
            # method to carve out exceptions so the OAuth session cookie set
            # on .com would survive to the callback. That's gone: everything,
            # including OAuth, runs on .org now. /health and /ready stay
            # exempt in case a healthcheck ever hits the .com hostname
            # directly — a 301 there wouldn't be followed and would read as
            # a failed check.
            if host_only == "affairsandorder.com" and request.path not in ("/health", "/ready"):
                canonical_host = "affairsandorder.org"
            if canonical_host and canonical_host != host_only:
                canonical = request.url.replace(
                    f"://{request.host}", f"://{canonical_host}" + (f":{port}" if port else ""), 1
                )
                return redirect(canonical, code=301)

        if os.getenv("RAILWAY_ENVIRONMENT_NAME") and request.path != "/health":
            forwarded_proto = request.headers.get("X-Forwarded-Proto", "http")
            if forwarded_proto != "https" and not request.is_secure:
                url = request.url.replace("http://", "https://", 1)
                return redirect(url, code=301)

        user_id = session.get("user_id")
        admin_ctrl_refresh_seconds = int(os.getenv("ADMIN_CTRL_REFRESH_SECONDS", "300"))
        if user_id:
            _ctrl_cache_ts = session.get("_admin_ctrl_ts", 0)
            _ctrl_stale = (time() - _ctrl_cache_ts) > admin_ctrl_refresh_seconds
            if _ctrl_stale:
                try:
                    with get_request_cursor() as _db:
                        _db.execute("SELECT COALESCE(session_epoch, 0) FROM users WHERE id = %s", (user_id,))
                        _epoch_row = _db.fetchone()
                        if _epoch_row is None:
                            session.clear()
                            return None
                        current_epoch = _epoch_row[0]
                        _db.execute("SELECT COALESCE(is_banned, FALSE), COALESCE(ban_reason, ''), COALESCE(kick_pending, FALSE) FROM admin_user_controls WHERE user_id = %s", (user_id,))
                        control_row = _db.fetchone()
                    session["_admin_ctrl"] = [
                        control_row[0] if control_row else False,
                        control_row[1] if control_row else "",
                        control_row[2] if control_row else False,
                        current_epoch,
                    ]
                    session["_admin_ctrl_ts"] = time()
                except Exception:
                    session["_admin_ctrl"] = None
                    session["_admin_ctrl_ts"] = time()
            control_row = session.get("_admin_ctrl")
            if control_row:
                # Defensive unpack: a session whose cache was populated by
                # the pre-session_epoch code (3-element list) may still be
                # live right at deploy time, within its up-to-300s cache
                # window. Fall back to the session's own embedded epoch
                # (trivially equal to itself, so no false kick) rather than
                # crashing on unpack -- it'll pick up the real DB epoch on
                # the next stale refresh.
                is_banned, ban_reason, kick_pending = control_row[0], control_row[1], control_row[2]
                current_epoch = control_row[3] if len(control_row) > 3 else session.get("session_epoch", 0)
                if is_banned:
                    session.clear()
                    return render_template("error.html", code=403, message=(f"Your account is banned. Reason: {ban_reason or 'No reason provided.'}")), 403
                # Real, unconditional invalidation: session_epoch is a
                # monotonic counter bumped by admin kick/ban and password
                # changes (database.bump_session_epoch). Unlike
                # kick_pending below -- a one-shot flag that whichever of a
                # user's concurrent sessions polls the DB first silently
                # consumes, leaving any other session on the same account
                # untouched -- this compares against live DB state every
                # time, so it kicks EVERY session carrying a stale value.
                # Sessions from before this feature existed have no
                # "session_epoch" key and default to 0, matching the
                # column's default, so a deploy alone never mass-logs-out.
                if session.get("session_epoch", 0) != current_epoch:
                    session.clear()
                    return redirect("/login")
                if kick_pending:
                    try:
                        with get_request_cursor() as _db:
                            _db.execute("UPDATE admin_user_controls SET kick_pending=FALSE, updated_at=NOW() WHERE user_id=%s", (user_id,))
                    except Exception: pass
                    session.clear()
                    return redirect("/login")
        if user_id:
            now = time()
            last_ping = session.get("_last_active_ping", 0)
            # Must stay well under the 5-minute window _hub_context() uses for
            # "Nations online now" (SELECT ... WHERE last_active > now() - '5
            # minutes') -- the old 3600s throttle meant an actively browsing
            # user showed as offline for up to ~55 minutes out of every hour.
            if now - last_ping > 120:
                try:
                    with get_request_cursor() as _db:
                        _db.execute("UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE id = %s", (user_id,))
                        from app_core.referrals.service import process_referral_activity
                        process_referral_activity(_db, user_id)
                    session["_last_active_ping"] = now
                except Exception: pass
        return None

    Compress(app)
    limiter.init_app(app)

    # Auth paths that must always be rate limited, even though they live
    # outside /api/ — brute-force/credential-stuffing targets.
    _RATE_LIMITED_AUTH_PATHS = (
        "/login",
        "/login/email",
        "/request_password_reset",
        "/account/request_password_reset",
        "/reset_password/",
        "/reset_password_recovery_key",
        "/discord_reset_password_page",
    )

    @limiter.request_filter
    def exempt_non_api_routes():
        # True means the request is EXEMPT from rate limiting.
        if request.path.startswith("/api/"):
            return False
        if request.path.startswith(_RATE_LIMITED_AUTH_PATHS):
            return False
        return True

    app.teardown_request(teardown_request_connection)

    @app.after_request
    def after_request(response):
        import logging
        logger = logging.getLogger(__name__)
        try:
            from time import time
            elapsed = time() - getattr(request, "start_time", time())
        except AttributeError:
            elapsed = 0
        if elapsed > 1.0 and not request.path.startswith("/static/"):
            client_ip = request.remote_addr
            ua = request.headers.get("User-Agent", "")
            logger.info("SLOW REQUEST: %s %s took %.2fs; ip=%s ua=%s", request.method, request.path, elapsed, client_ip, ua[:200])
        if request.path.startswith("/static/"):
            if request.path.endswith((".css", ".js")):
                response.headers["Cache-Control"] = "public, max-age=3600, must-revalidate"
            else:
                response.headers["Cache-Control"] = "public, max-age=604800, must-revalidate"
        else:
            response.headers["Cache-Control"] = "private, max-age=5, must-revalidate"

        # Security headers
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        # CSP: allow same-origin + trusted CDNs used by the game.
        # Both apex domains are whitelisted for scripts/styles/fonts/xhr because
        # the OAuth signup pages are served on .com while their /static assets
        # 301-redirect to .org (Cloudflare-cached). Without the sibling domain
        # in style-src/script-src, those redirected assets are CSP-blocked and
        # the signup page renders completely unstyled (player-reported).
        _sites = "https://affairsandorder.org https://affairsandorder.com"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            f"script-src 'self' 'unsafe-inline' {_sites} https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            f"style-src 'self' 'unsafe-inline' {_sites} https://fonts.googleapis.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com data:; "
            "img-src 'self' data: https: blob:; "
            "media-src 'self' https:; "
            "frame-src 'self' https://www.youtube.com https://player.vimeo.com; "
            f"connect-src 'self' {_sites}; "
            "object-src 'none'; "
            "base-uri 'self';"
        )
        return response

    def asset(filename):
        is_production = (os.getenv("FLASK_ENV") == "production" or os.getenv("RAILWAY_ENVIRONMENT_NAME") is not None)
        if is_production and (filename.endswith(".css") or filename.endswith(".js")):
            base, ext = filename.rsplit(".", 1)
            minified = f"{base}.min.{ext}"
            min_path = f"static/{minified}"
            if os.path.exists(min_path):
                return minified
        return filename
    app.jinja_env.globals["asset"] = asset

    logging_format = "====\\n%(levelname)s (%(created)f - %(asctime)s) (LINE %(lineno)d - %(filename)s - %(funcName)s): %(message)s"
    logging.basicConfig(level=logging.ERROR, format=logging_format, filename="errors.log")
    logger = logging.getLogger(__name__)

    import threading, queue as queue_module
    _webhook_queue = queue_module.Queue()
    _webhook_thread = None
    _webhook_thread_lock = threading.Lock()

    def _webhook_worker():
        while True:
            try:
                data = _webhook_queue.get(timeout=5)
                if data is None: break
                url = os.getenv("DISCORD_WEBHOOK_URL")
                if url:
                    try: requests.post(url, json=data, timeout=5)
                    except Exception: pass
                _webhook_queue.task_done()
            except queue_module.Empty:
                continue

    def _ensure_webhook_thread():
        nonlocal _webhook_thread
        with _webhook_thread_lock:
            if _webhook_thread is None or not _webhook_thread.is_alive():
                _webhook_thread = threading.Thread(target=_webhook_worker, daemon=True)
                _webhook_thread.start()

    def send_discord_webhook(record):
        url = os.getenv("DISCORD_WEBHOOK_URL")
        if not url: return
        formatter = logging.Formatter(logging_format)
        message = formatter.format(record)
        if len(message) > 1900: message = message[:1900] + "...[truncated]"
        data = {"content": message, "username": "A&O ERROR"}
        _ensure_webhook_thread()
        try: _webhook_queue.put_nowait(data)
        except queue_module.Full: pass

    class RequestsHandler(logging.Handler):
        def emit(self, record):
            send_discord_webhook(record)

    Markdown(app)

    @app.template_filter("richmedia")
    def richmedia_filter(text):
        """Render a rich page description: markdown (links, images, formatting)
        plus responsive YouTube/Vimeo embeds for bare video links.

        Video iframes are built only from a validated id extracted from
        whitelisted hosts, so the src can never be attacker-controlled beyond
        those hosts (which the CSP frame-src already permits).
        """
        import re
        import markdown as _md
        from markupsafe import Markup

        if not text:
            return Markup("")

        yt = re.compile(
            r"(?:https?://)?(?:www\.|m\.)?(?:"
            r"youtube\.com/(?:watch\?(?:.*&)?v=|embed/|shorts/|live/)|"
            r"youtu\.be/"
            r")([A-Za-z0-9_-]{11})[^\s]*"
        )
        vimeo = re.compile(r"(?:https?://)?(?:www\.)?vimeo\.com/(\d+)[^\s]*")

        placeholders = []

        def _stash(html):
            token = f"\n\nVIDEOEMBED{len(placeholders)}ENDEMBED\n\n"
            placeholders.append(html)
            return token

        def _yt(m):
            vid = m.group(1)
            return _stash(
                '<div class="rich-video"><iframe src="https://www.youtube.com/embed/'
                f'{vid}" title="YouTube video" frameborder="0" allowfullscreen '
                'loading="lazy"></iframe></div>'
            )

        def _vimeo(m):
            vid = m.group(1)
            return _stash(
                '<div class="rich-video"><iframe src="https://player.vimeo.com/video/'
                f'{vid}" title="Vimeo video" frameborder="0" allowfullscreen '
                'loading="lazy"></iframe></div>'
            )

        text = yt.sub(_yt, text)
        text = vimeo.sub(_vimeo, text)

        html = _md.markdown(text, extensions=["nl2br"])

        # Sanitize the user-derived markdown output BEFORE splicing in the
        # trusted, server-built video-embed HTML below — bleach would strip
        # the iframes too since they aren't on the allowlist.
        import bleach

        allowed_tags = [
            "p", "br", "strong", "em", "b", "i", "u", "ul", "ol", "li",
            "a", "blockquote", "code", "pre", "h1", "h2", "h3", "img",
        ]
        allowed_attrs = {
            "a": ["href", "title", "rel"],
            "img": ["src", "alt", "title"],
        }
        html = bleach.clean(
            html, tags=allowed_tags, attributes=allowed_attrs, strip=True
        )
        html = bleach.linkify(html)

        for i, embed in enumerate(placeholders):
            html = html.replace(f"<p>VIDEOEMBED{i}ENDEMBED</p>", embed)
            html = html.replace(f"VIDEOEMBED{i}ENDEMBED", embed)
        return Markup(html)

    # Initialize province defaults
    try:
        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute("UPDATE provinces SET happiness=50 WHERE happiness=0")
            db.execute("UPDATE provinces SET productivity=50 WHERE productivity=0")
            db.execute("UPDATE provinces SET consumer_spending=50 WHERE consumer_spending=0")
            conn.commit()
    except Exception as e:
        pass

    # Root route registrations
    signup.register_signup_routes(app)
    login.register_login_routes(app)

    from login_verification import register_login_verification_routes
    register_login_verification_routes(app)

    # Google Auth Registration
    from app_core.auth.google_auth import register_google_auth_routes
    register_google_auth_routes(app)
    
    change.register_change_routes(app)
    bot_api.register_bot_api_routes(app)
    countries.register_countries_routes(app)
    policies.register_policies_routes(app)
    statistics.register_statistics_routes(app)
    register_trade_agreement_routes(app)
    app.register_blueprint(province.bp)
    if upgrades_bp: app.register_blueprint(upgrades_bp)
    app.register_blueprint(intelligence.bp)
    app.register_blueprint(wars_bp)
    app.register_blueprint(treaties_bp)

    # App Core DDD Registrations
    from app_core.main.routes import bp as main_bp
    from app_core.auth.routes import bp as auth_bp
    from app_core.game_engine.routes import bp as game_engine_bp
    from app_core.system.routes import bp as system_bp
    from app_core.admin.routes import admin_bp
    from app_core.ads.routes import bp as ads_bp
    from app_core.world_map.routes import bp as world_map_bp
    from app_core.game_map.routes import bp as game_map_bp
    from app_core.market.routes import market_bp
    from app_core.store.routes import (
        store_bp,
        stripe_webhook as store_stripe_webhook,
        bmc_webhook as store_bmc_webhook,
    )
    from app_core.military.routes import bp as military_bp
    from app_core.coalitions.routes import register_coalitions_routes
    from app_core.tutorial.routes import bp as tutorial_api_bp
    from app_core.referrals.routes import bp as referrals_api_bp
    from app_core.onboarding.routes import bp as onboarding_api_bp
    from app_core.events.routes import events_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    from app_core.auth.email_auth import email_auth_bp
    app.register_blueprint(email_auth_bp)

    app.register_blueprint(game_engine_bp)
    app.register_blueprint(system_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(ads_bp)
    app.register_blueprint(world_map_bp)
    app.register_blueprint(game_map_bp)
    app.register_blueprint(market_bp)
    app.register_blueprint(store_bp)
    app.register_blueprint(military_bp)
    app.register_blueprint(tutorial_api_bp)
    app.register_blueprint(referrals_api_bp)
    app.register_blueprint(onboarding_api_bp)
    app.register_blueprint(events_bp)
    register_coalitions_routes(app)

    import config
    config.validate_production_secrets()
    config.warn_optional_integrations()
    try:
        if hasattr(signup, "ensure_signup_attempts_table"):
            signup.ensure_signup_attempts_table()
    except Exception:
        pass

    environment = os.getenv("ENVIRONMENT", "DEV")
    app.secret_key = config.get_secret_key()

    from flask_wtf.csrf import CSRFProtect, CSRFError

    # 24-hour token lifetime so players who keep a tab open don't get 400s
    app.config["WTF_CSRF_TIME_LIMIT"] = 86400

    csrf = CSRFProtect(app)
    csrf.exempt(bot_api.bp)
    # Only the webhook view, not the whole store_bp blueprint — the rest of
    # store_bp is player-facing and must keep normal CSRF protection. The
    # webhook's auth boundary is the Stripe signature check inside the view.
    csrf.exempt(store_stripe_webhook)
    csrf.exempt(store_bmc_webhook)

    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        return render_template(
            "error.html",
            code=400,
            message="Your session form expired. Please go back and try again.",
        ), 400
    if environment == "PROD":
        handler = RequestsHandler()
        logger.addHandler(handler)

    @app.context_processor
    def inject_rotating_ads():
        """Approved player banner ads for the side rails (cached in helper)."""
        try:
            from app_core.ads.helpers import load_rotating_ads
            from database import get_db_cursor

            return {"rotating_ads": load_rotating_ads(get_db_cursor)}
        except Exception:
            return {"rotating_ads": {}}

    @app.context_processor
    def utility_processor():
        def humanize_number(value):
            if value is None: return "0"
            try: return f"{int(value):,}"
            except (ValueError, TypeError): return str(value)
        def determine_color(change_val):
            if change_val > 0: return "green"
            elif change_val < 0: return "red"
            else: return "white"
        def format_resources(value):
            if value is None: return "0"
            try: return f"{float(value):.2f}"
            except (ValueError, TypeError): return str(value)
        def format_currency(value):
            if value is None: return "$0.00"
            try: return f"${float(value):,.2f}"
            except (ValueError, TypeError): return str(value)
        return dict(
            humanize_number=humanize_number,
            determine_color=determine_color,
            format_resources=format_resources,
            format_currency=format_currency,
        )

    from app_core.admin.services import SUPER_ADMIN_USER_IDS

    def get_resources():
        """User resource HUD values for layout templates."""
        default_resources = {
            "gold": 0,
            "rations": 0,
            "oil": 0,
            "coal": 0,
            "uranium": 0,
            "bauxite": 0,
            "iron": 0,
            "lead": 0,
            "copper": 0,
            "lumber": 0,
            "components": 0,
            "steel": 0,
            "consumer_goods": 0,
            "aluminium": 0,
            "gasoline": 0,
            "ammunition": 0,
        }
        target_user_id = session.get("user_id")
        if not target_user_id:
            return default_resources

        cache_key = f"resources_{target_user_id}"
        cached = query_cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            with get_db_cursor(cursor_factory=RealDictCursor) as db:
                db.execute("SELECT gold FROM stats WHERE id=%s", (target_user_id,))
                gold_row = db.fetchone()
                if gold_row:
                    default_resources["gold"] = gold_row.get("gold", 0) or 0

                db.execute(
                    """
                    SELECT rd.name, COALESCE(ue.quantity, 0) AS quantity
                    FROM resource_dictionary rd
                    LEFT JOIN user_economy ue
                      ON ue.resource_id = rd.resource_id
                     AND ue.user_id = %s
                    ORDER BY rd.resource_id
                    """,
                    (target_user_id,),
                )
                rows = db.fetchall()
                resources = default_resources.copy()
                for row in rows:
                    name = row.get("name")
                    if name in resources:
                        resources[name] = int(row.get("quantity") or 0)

                query_cache.set(cache_key, resources, ttl_seconds=15)
                return resources
        except Exception:
            return default_resources

    def get_notification_count():
        """Real unread-news count for the topbar bell badge (see /api/notifications
        for the dropdown's actual content). Same table country.html's own
        Reports & News section reads/dismisses from (news.destination_id), so
        this count naturally drops as the player dismisses items there.
        """
        target_user_id = session.get("user_id")
        if not target_user_id:
            return 0

        cache_key = f"notif_count_{target_user_id}"
        cached = query_cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            with get_db_cursor() as db:
                db.execute("SELECT COUNT(*) FROM news WHERE destination_id=%s", (target_user_id,))
                count = db.fetchone()[0] or 0
                query_cache.set(cache_key, count, ttl_seconds=15)
                return count
        except Exception:
            return 0

    @app.context_processor
    def inject_layout_context():
        """Single layout context: game UI, admin ids, and per-user HUD data."""
        try:
            from tests.conftest import TEST_UI_MOCK_CONTEXT

            if TEST_UI_MOCK_CONTEXT.get("active"):
                return TEST_UI_MOCK_CONTEXT.get("context", {})
        except ImportError:
            pass

        from app_core.auth.google_auth import is_google_auth_configured

        ctx = {
            **game_ui.game_ui_context(),
            "google_client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "google_auth_enabled": is_google_auth_configured(),
            "admin_user_ids": list(SUPER_ADMIN_USER_IDS),
            "get_resources": get_resources,
            "notification_count": get_notification_count(),
            "game_ui": {},
            "equipped_bg_css_class": None,
        }

        if "user_id" not in session:
            return ctx

        user_id = session["user_id"]
        cache_key = f"layout_user_{user_id}"
        cached_user = query_cache.get(cache_key)

        try:
            with get_request_cursor() as db:
                if cached_user is None:
                    try:
                        from database import get_coalition_members_table

                        members_tbl = get_coalition_members_table()
                        if members_tbl:
                            db.execute(
                                f"""
                                SELECT u.username, cn.id as col_id, cn.name as col_name
                                FROM users u
                                LEFT JOIN {members_tbl} cm ON cm.userid = u.id
                                LEFT JOIN colnames cn ON cn.id = cm.colid
                                WHERE u.id = %s
                                """,
                                (user_id,),
                            )
                        else:
                            db.execute(
                                "SELECT username, NULL, NULL FROM users WHERE id = %s",
                                (user_id,),
                            )
                        row = db.fetchone()

                        if row:
                            cached_user = {
                                "country_name": row[0] if row[0] else "Unknown",
                                "coalition_id": row[1],
                                "coalition_name": row[2],
                                # Cosmetics (equipped background) aren't implemented in the
                                # schema yet (no cosmetics table, no
                                # stats.equipped_background_cosmetic_id column) -- this was
                                # previously joining against tables/columns that don't exist,
                                # which threw on every request and, worse, rolled back this
                                # request's whole shared connection, silently discarding any
                                # earlier uncommitted write in the same request (found via a
                                # real repro: a DM's read-receipt write vanishing on render).
                                "equipped_bg_css_class": None,
                            }
                        else:
                            cached_user = {
                                "country_name": "Unknown",
                                "coalition_id": None,
                                "coalition_name": None,
                                "equipped_bg_css_class": None,
                            }
                        query_cache.set(cache_key, cached_user, ttl_seconds=60)
                    except Exception:
                        rollback_db_cursor(db)
                        cached_user = {
                            "country_name": "Error",
                            "coalition_id": None,
                            "coalition_name": None,
                            "equipped_bg_css_class": None,
                        }

                ctx["country_name"] = cached_user["country_name"]
                ctx["coalition_id"] = cached_user["coalition_id"]
                ctx["coalition_name"] = cached_user["coalition_name"]
                ctx["equipped_bg_css_class"] = cached_user.get("equipped_bg_css_class")

                # Store cosmetics: cosmetics/stats.equipped_background_cosmetic_id
                # only exist once migration 0048 has run, which is exactly the
                # gate FEATURE_STORE already gives us (Dede won't flip it on
                # until the migration is applied) -- keeps this query from ever
                # running against a schema that doesn't have it yet (see the
                # equipped_bg_css_class incident above for why that matters).
                if game_ui.FEATURE_STORE or user_id in SUPER_ADMIN_USER_IDS:
                    equip_cache_key = f"layout_user_equip_{user_id}"
                    cached_equip = query_cache.get(equip_cache_key)
                    if cached_equip is None:
                        try:
                            from app_core.store.repositories import get_equipped_cosmetic

                            cached_equip = {"css_class": get_equipped_cosmetic(db, user_id)}
                            query_cache.set(equip_cache_key, cached_equip, ttl_seconds=60)
                        except Exception:
                            rollback_db_cursor(db)
                            cached_equip = {"css_class": None}
                    ctx["equipped_bg_css_class"] = cached_equip["css_class"]

                ctx["game_ui"] = {"has_unseen_combat_logs": False}
                try:
                    from app_core.onboarding.service import get_onboarding_status

                    ctx["onboarding_checklist"] = get_onboarding_status(db, user_id)
                except Exception:
                    # Swallowing without rolling back would leave this request's
                    # shared connection in an aborted-transaction state for
                    # everything after it (any earlier uncommitted write in this
                    # request would then be silently discarded, since a COMMIT
                    # on an aborted postgres transaction is treated as a ROLLBACK
                    # -- found via a real repro, not theoretical).
                    rollback_db_cursor(db)
                    ctx["onboarding_checklist"] = None
        except Exception:
            ctx["country_name"] = "Error"
            ctx["coalition_id"], ctx["coalition_name"] = None, None
            ctx["game_ui"] = {"has_unseen_combat_logs": False}

        return ctx


    @app.template_filter()
    def nav_initials(name):
        """"Empire of Rome" -> "ER" (skips short filler words); a single-word
        name like "Meridia" -> "ME" (first two letters) -- matches the
        redesigned topbar avatar's convention (see /Users/dede/ano-redesign/
        shell.js's initials()).
        """
        if not name:
            return "?"
        skip = {"of", "the", "and", "de", "la"}
        words = [w for w in str(name).split() if w.lower() not in skip]
        if len(words) >= 2:
            return (words[0][0] + words[1][0]).upper()
        return str(name)[:2].upper()

    # --- RESTORED JINJA2 FILTERS ---
    @app.template_filter()
    def commas(value):
        try:
            rounded = round(value)
            returned = "{:,}".format(rounded)
        except (TypeError, ValueError):
            returned = value
        return returned

    @app.template_filter()
    def fmt(value):
        try:
            num = float(value)
            if num < 0: return "-" + fmt(abs(num))
            if num < 10000:
                if num == int(num): return "{:,}".format(int(num))
                return "{:,.2f}".format(num)
            elif num < 1000000:
                k = num / 1000
                if k == int(k): return "{:,}K".format(int(k))
                return "{:,.2f}".format(k).rstrip("0").rstrip(".") + "K"
            elif num < 1000000000:
                m = num / 1000000
                if m == int(m): return "{}M".format(int(m))
                return "{:.2f}M".format(m).rstrip("0").rstrip(".")
            else:
                b = num / 1000000000
                if b == int(b): return "{}B".format(int(b))
                return "{:.2f}B".format(b).rstrip("0").rstrip(".")
        except (TypeError, ValueError): return value

    @app.template_filter()
    def weight_fmt(value):
        try:
            num = float(value)
            if num < 0: return "-" + weight_fmt(abs(num))
            if num < 1000:
                if num == int(num): return "{:,} kg".format(int(num))
                return "{:,.2f} kg".format(num)
            elif num < 1000000:
                t = num / 1000
                if t == int(t): return "{:,} t".format(int(t))
                return "{:,.2f} t".format(t)
            elif num < 1000000000:
                kt = num / 1000000
                if kt == int(kt): return "{:,} kt".format(int(kt))
                return "{:,.2f} kt".format(kt)
            else:
                mt = num / 1000000000
                if mt == int(mt): return "{:,} Mt".format(int(mt))
                return "{:,.2f} Mt".format(mt)
        except (TypeError, ValueError): return value

    @app.template_filter()
    def days_old(date_string):
        try:
            from datetime import datetime as _dt
            date_obj = _dt.strptime(str(date_string), "%Y-%m-%d")
            today = _dt.today()
            delta = today - date_obj
            return f"{date_string} ({delta.days} Days Old)"
        except (ValueError, TypeError): return date_string

    @app.template_filter()
    def timeago(value):
        if value is None: return "Never"
        try:
            from datetime import datetime, timezone
            if isinstance(value, str): value = datetime.fromisoformat(value)
            if value.tzinfo is None: value = value.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            diff = now - value
            seconds = int(diff.total_seconds())
            if seconds < 60: return "Just now"
            minutes = seconds // 60
            if minutes < 60: return f"{minutes}m ago"
            hours = minutes // 60
            if hours < 24: return f"{hours}h ago"
            days = hours // 24
            if days < 30: return f"{days}d ago"
            months = days // 30
            if months < 12: return f"{months}mo ago"
            years = days // 365
            return f"{years}y ago"
        except Exception: return "Unknown"

    @app.template_filter()
    def prores(unit):
        try:
            from app_core.economy.building_costs import get_build_cost

            change_price = False
            raw = unit
            if "," in unit:
                split_unit = unit.split(", ")
                raw = split_unit[0]
                change_price = float(split_unit[1])
            cost = get_build_cost(raw)
            if change_price != 1.0 and change_price:
                scaled_gold = int(cost["gold"] * change_price)
                cost["cost_display"] = cost["cost_display"].replace(
                    fmt(cost["gold"]), fmt(scaled_gold), 1
                )
            return cost["cost_display"]
        except Exception:
            return unit

    @app.template_filter()
    def milres(unit):
        try:
            from variables import MILDICT
            change_price = False
            if "," in unit:
                split_unit = unit.split(", ")
                unit = split_unit[0]
                change_price = float(split_unit[1])
            price = MILDICT[unit]["price"]
            if change_price: price = price * change_price
            manpower = MILDICT[unit].get("manpower", 0)
            try:
                res_parts = [f"{weight_fmt(i[1])} {i[0]}" for i in MILDICT[unit]["resources"].items()]
                resources = ", ".join(res_parts)
                return f"{unit.capitalize()} cost {fmt(price)} gold, {manpower} manpower, {resources} each"
            except KeyError:
                return f"{unit.capitalize()} cost {fmt(price)} gold, {manpower} manpower each"
        except Exception: return unit

    @app.template_filter()
    def formatname(value):
        if not isinstance(value, str): return value
        if value.lower() == "citycount": return "City"
        return value.replace("_", " ").title()
    # --- END RESTORED FILTERS ---

    from extensions import socketio
    from app_core.chat.routes import register_chat_routes, register_chat_socketio_handlers
    from app_core.community.routes import register_community_routes

    register_chat_routes(app)
    register_chat_socketio_handlers(socketio)
    register_community_routes(app)
    _socketio_debug = os.getenv("ANO_SOCKETIO_DEBUG") == "1"
    socketio.init_app(
        app,
        message_queue=config.get_redis_url(),
        logger=_socketio_debug,
        engineio_logger=_socketio_debug,
    )

    return app

create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, use_reloader=False)
