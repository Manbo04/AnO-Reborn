import ast
import sys
import os
import json
import hmac
import time as time_module
from flask import Flask, request, render_template, session, redirect, send_from_directory
from flask_compress import Compress
import traceback

# Root modules
import upgrades
import intelligence
import change
import countries
import signup
import login
from wars.routes import wars_bp
from treaties import treaties_bp
import policies
import statistics
import requests
import trade_agreements
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

app = Flask(__name__)

def create_app():
    global app
    app.url_map.strict_slashes = False

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
        return render_template("error.html", code=403, message="Forbidden: 403 error handler triggered."), 403

    app.config["PREFERRED_URL_SCHEME"] = "https"
    app.config["SERVER_NAME"] = None
    app.config["ALLOWED_HOSTS"] = ["affairsandorder.com", "www.affairsandorder.com", "web-production-55d7b.up.railway.app"]
    app.config["SESSION_COOKIE_DOMAIN"] = None
    app.config["SESSION_COOKIE_SAMESITE"] = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    app.config["SESSION_COOKIE_SECURE"] = (os.getenv("ENVIRONMENT") == "PROD" and os.getenv("RAILWAY_ENVIRONMENT_NAME") is not None)

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
                        _db.execute("SELECT COALESCE(is_banned, FALSE), COALESCE(ban_reason, ''), COALESCE(kick_pending, FALSE) FROM admin_user_controls WHERE user_id = %s", (user_id,))
                        control_row = _db.fetchone()
                    session["_admin_ctrl"] = list(control_row) if control_row else None
                    session["_admin_ctrl_ts"] = time()
                except Exception:
                    session["_admin_ctrl"] = None
                    session["_admin_ctrl_ts"] = time()
            control_row = session.get("_admin_ctrl")
            if control_row:
                is_banned, ban_reason, kick_pending = control_row
                if is_banned:
                    session.clear()
                    return render_template("error.html", code=403, message=(f"Your account is banned. Reason: {ban_reason or 'No reason provided.'}")), 403
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
            if now - last_ping > 3600:
                try:
                    with get_request_cursor() as _db:
                        _db.execute("UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE id = %s", (user_id,))
                    session["_last_active_ping"] = now
                except Exception: pass
        return None

    Compress(app)
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
            client_ip = request.headers.get("X-Forwarded-For") or request.remote_addr
            ua = request.headers.get("User-Agent", "")
            logger.info("SLOW REQUEST: %s %s took %.2fs; ip=%s ua=%s", request.method, request.path, elapsed, client_ip, ua[:200])
        if request.path.startswith("/static/"):
            if request.path.endswith((".css", ".js")):
                response.headers["Cache-Control"] = "public, max-age=3600, must-revalidate"
            else:
                response.headers["Cache-Control"] = "public, max-age=604800, must-revalidate"
        else:
            response.headers["Cache-Control"] = "private, max-age=5, must-revalidate"
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
    
    # Google Auth Registration
    from app_core.auth.google_auth import register_google_auth_routes
    register_google_auth_routes(app)
    
    change.register_change_routes(app)
    bot_api.register_bot_api_routes(app)
    countries.register_countries_routes(app)
    policies.register_policies_routes(app)
    statistics.register_statistics_routes(app)
    trade_agreements.register_trade_agreement_routes(app)
    app.register_blueprint(province.bp)
    if upgrades.bp: app.register_blueprint(upgrades.bp)
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
    from app_core.market.routes import market_bp
    from app_core.military.routes import bp as military_bp
    from app_core.coalitions.routes import register_coalitions_routes

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    from app_core.auth.email_auth import email_auth_bp
    app.register_blueprint(email_auth_bp)

    app.register_blueprint(game_engine_bp)
    app.register_blueprint(system_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(ads_bp)
    app.register_blueprint(world_map_bp)
    app.register_blueprint(market_bp)
    app.register_blueprint(military_bp)
    register_coalitions_routes(app)

    import config
    try:
        if hasattr(signup, "ensure_signup_attempts_table"):
            signup.ensure_signup_attempts_table()
    except Exception:
        pass

    environment = os.getenv("ENVIRONMENT", "DEV")
    app.secret_key = config.get_secret_key()
    if environment == "PROD":
        handler = RequestsHandler()
        logger.addHandler(handler)

    @app.context_processor
    def utility_processor():
        google_client_id = os.getenv("GOOGLE_CLIENT_ID")
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
            google_client_id=google_client_id,
            humanize_number=humanize_number,
            determine_color=determine_color,
            format_resources=format_resources,
            format_currency=format_currency,
        )

    # game_ui_context setup
    from database import get_request_cursor, rollback_db_cursor

    def _get_user_game_context():
        try:
            from tests.conftest import TEST_UI_MOCK_CONTEXT
            if TEST_UI_MOCK_CONTEXT.get("active"): return TEST_UI_MOCK_CONTEXT.get("context", {})
        except ImportError: pass
        if "user_id" not in session: return {}
        user_id = session["user_id"]
        ctx = {}
        with get_request_cursor() as _db:
            try:
                _db.execute("SELECT countryName FROM users WHERE id = %s", (user_id,))
                r = _db.fetchone()
                ctx["country_name"] = r[0] if r else "Unknown"
                _db.execute("SELECT id, name FROM colNames WHERE id = (SELECT coalitionId FROM users WHERE id=%s)", (user_id,))
                c_row = _db.fetchone()
                if c_row: ctx["coalition_id"], ctx["coalition_name"] = c_row[0], c_row[1]
                else: ctx["coalition_id"], ctx["coalition_name"] = None, None
            except Exception:
                rollback_db_cursor(_db)
                ctx["country_name"], ctx["coalition_id"], ctx["coalition_name"] = "Error", None, None
        return ctx

    app.context_processor(_get_user_game_context)

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

        with get_db_cursor(cursor_factory=RealDictCursor) as db:
            try:
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

    # Global context for inject_global_data
    @app.context_processor
    def inject_global_data():
        if "user_id" not in session: return {"game_ui": {}}
        user_id = session["user_id"]
        from database import get_request_cursor, rollback_db_cursor
        with get_request_cursor() as cur:
            try:
                cur.execute("SELECT has_unseen_combat_logs FROM users WHERE id = %s", (user_id,))
                row = cur.fetchone()
                has_combat = row[0] if row else False
            except Exception:
                rollback_db_cursor(cur)
                has_combat = False
        return {"game_ui": {"has_unseen_combat_logs": has_combat}}

    @app.context_processor
    def inject_user():
        google_client_id = os.getenv("GOOGLE_CLIENT_ID")
        top_ad = None
        side_ad_left = None
        side_ad_right = None
        try:
            from database import get_request_cursor
            with get_request_cursor(read_only=True) as db:
                db.execute("SELECT image_url, target_url FROM advertisements WHERE status = 'approved' AND ad_type = 'top' ORDER BY RANDOM() LIMIT 1")
                top_ad_row = db.fetchone()
                if top_ad_row:
                    top_ad = {"image_url": top_ad_row[0], "target_url": top_ad_row[1]}
                db.execute("SELECT image_url, target_url FROM advertisements WHERE status = 'approved' AND ad_type = 'side' ORDER BY RANDOM() LIMIT 2")
                side_ads = db.fetchall()
                if side_ads:
                    side_ad_left = {"image_url": side_ads[0][0], "target_url": side_ads[0][1]}
                    if len(side_ads) > 1:
                        side_ad_right = {"image_url": side_ads[1][0], "target_url": side_ads[1][1]}
        except Exception:
            pass

        return dict(
            google_client_id=google_client_id,
            top_ad=top_ad,
            side_ad_left=side_ad_left,
            side_ad_right=side_ad_right,
            get_resources=get_resources,
            **game_ui.game_ui_context(),
            **_get_user_game_context()
        )


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
                return "{:,.1f}".format(num)
            elif num < 1000000:
                k = num / 1000
                if k == int(k): return "{:,}K".format(int(k))
                return "{:,.1f}".format(k).rstrip("0").rstrip(".") + "K"
            elif num < 1000000000:
                m = num / 1000000
                if m == int(m): return "{}M".format(int(m))
                return "{:.1f}M".format(m).rstrip("0").rstrip(".")
            else:
                b = num / 1000000000
                if b == int(b): return "{}B".format(int(b))
                return "{:.1f}B".format(b).rstrip("0").rstrip(".")
        except (TypeError, ValueError): return value

    @app.template_filter()
    def weight_fmt(value):
        try:
            num = float(value)
            if num < 0: return "-" + weight_fmt(abs(num))
            if num < 1000:
                if num == int(num): return "{:,} kg".format(int(num))
                return "{:,.1f} kg".format(num)
            elif num < 1000000:
                t = num / 1000
                if t == int(t): return "{:,} t".format(int(t))
                return "{:,.1f} t".format(t)
            elif num < 1000000000:
                kt = num / 1000000
                if kt == int(kt): return "{:,} kt".format(int(kt))
                return "{:,.1f} kt".format(kt)
            else:
                mt = num / 1000000000
                if mt == int(mt): return "{:,} Mt".format(int(mt))
                return "{:,.1f} Mt".format(mt)
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
            from variables import PROVINCE_UNIT_PRICES
            change_price = False
            unit = unit.lower()
            if "," in unit:
                split_unit = unit.split(", ")
                unit = split_unit[0]
                change_price = float(split_unit[1])
            renames = {"Fulfillment centers": "malls", "Bullet trains": "monorails"}
            unit_name = unit.replace("_", " ").capitalize()
            if unit_name == "Coal burners": unit_name = "Coal power plants"
            try: unit = renames[unit_name]
            except KeyError: pass
            price = PROVINCE_UNIT_PRICES[f"{unit}_price"]
            if change_price: price = price * change_price
            try:
                res_parts = [f"{weight_fmt(i[1])} {i[0]}" for i in PROVINCE_UNIT_PRICES[f"{unit}_resource"].items()]
                resources = ", ".join(res_parts)
                return f"{unit_name} cost {fmt(price)}, {resources} each"
            except KeyError:
                return f"{unit_name} cost {fmt(price)} each"
        except Exception: return unit

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
            try:
                res_parts = [f"{weight_fmt(i[1])} {i[0]}" for i in MILDICT[unit]["resources"].items()]
                resources = ", ".join(res_parts)
                return f"{unit.capitalize()} cost {fmt(price)}, {resources} each"
            except KeyError:
                return f"{unit.capitalize()} cost {fmt(price)} each"
        except Exception: return unit

    @app.template_filter()
    def formatname(value):
        if not isinstance(value, str): return value
        if value.lower() == "citycount": return "City"
        return value.replace("_", " ").title()
    # --- END RESTORED FILTERS ---
    return app

create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, use_reloader=False)
