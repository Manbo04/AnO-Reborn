import ast
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if not hasattr(ast, "Str"):
    ast.Str = ast.Constant
if not hasattr(ast, "Num"):
    ast.Num = ast.Constant
if not hasattr(ast, "NameConstant"):
    ast.NameConstant = ast.Constant
if not hasattr(ast, "Ellipsis"):
    ast.Ellipsis = ast.Constant
import ast
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if not hasattr(ast, "Str"):
    ast.Str = ast.Constant
if not hasattr(ast, "Num"):
    ast.Num = ast.Constant
if not hasattr(ast, "NameConstant"):
    ast.NameConstant = ast.Constant
if not hasattr(ast, "Ellipsis"):
    ast.Ellipsis = ast.Constant

from flask import Flask, request, render_template, session, redirect, send_from_directory
import traceback
import os
from dotenv import load_dotenv
load_dotenv()


app = Flask(__name__)




# Debug test route for logging verification (must be after app is defined)
## Only one debugtest route should exist, after app = Flask(__name__)

# Add global 403 error handler after app is defined
@app.errorhandler(403)
def forbidden_error(error):
    import logging
    logger = logging.getLogger(__name__)
    logger.error(f"[DEBUG] 403 error handler triggered: {error}")
    return render_template("error.html", code=403, message="Forbidden: 403 error handler triggered."), 403

# Configure trusted hosts for domain setup
# This allows Flask to work with custom domains via reverse proxy
app.config['PREFERRED_URL_SCHEME'] = 'https'
app.config['SERVER_NAME'] = None  # Allow dynamic hostnames via proxy headers
app.config['ALLOWED_HOSTS'] = ['affairsandorder.com', 'www.affairsandorder.com', 'web-production-55d7b.up.railway.app']

# Trust X-Forwarded-* headers from Railway reverse proxy
@app.before_request
def before_request():
    # Ensure HTTPS is used (check X-Forwarded-Proto for reverse proxy)
    if os.getenv('RAILWAY_ENVIRONMENT_NAME'):
        forwarded_proto = request.headers.get('X-Forwarded-Proto', 'http')
        if forwarded_proto != 'https' and not request.is_secure:
            url = request.url.replace('http://', 'https://', 1)
            return redirect(url, code=301)

# Import cache_response decorator
from database import cache_response

# Performance: Enable gzip compression for responses
try:
    from flask_compress import Compress
    Compress(app)
except ImportError:
    # Flask-Compress not installed, continue without it
    pass

# Performance: Add caching headers for static files
@app.after_request
def add_cache_headers(response):
    # Cache static assets for 1 month (2592000 seconds)
    if request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'public, max-age=2592000, immutable'
    # Cache images for 1 month
    elif request.path.endswith(('.jpg', '.png', '.gif', '.ico')):
        response.headers['Cache-Control'] = 'public, max-age=2592000'
    # Don't cache HTML pages (they might change)
    else:
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

# Helper to get minified asset path in production
def asset(filename):
    """Returns minified version of asset in production, original in development"""
    import os
    is_production = os.getenv('FLASK_ENV') == 'production' or os.getenv('RAILWAY_ENVIRONMENT_NAME') is not None
    
    if is_production and (filename.endswith('.css') or filename.endswith('.js')):
        base, ext = filename.rsplit('.', 1)
        minified = f"{base}.min.{ext}"
        min_path = f"static/{minified}"
        if os.path.exists(min_path):
            return minified
    
    return filename

# Make asset helper available in templates
app.jinja_env.globals['asset'] = asset

import upgrades
import intelligence
import tasks
import market
import province
import military
import change
import coalitions
import countries
import signup
import login
from wars.routes import wars_bp
import policies
import statistics
import requests
import logging
from variables import MILDICT, PROVINCE_UNIT_PRICES
from flaskext.markdown import Markdown
from psycopg2.extras import RealDictCursor
from datetime import datetime as dt
import string
import random
import os
from helpers import login_required
from database import get_db_cursor
import psycopg2
from dotenv import load_dotenv
load_dotenv()


# LOGGING
logging_format = '====\n%(levelname)s (%(created)f - %(asctime)s) (LINE %(lineno)d - %(filename)s - %(funcName)s): %(message)s'
logging.basicConfig(level=logging.ERROR,
                    format=logging_format, filename='errors.log',)
logger = logging.getLogger(__name__)


class RequestsHandler(logging.Handler):
    def send_discord_webhook(self, record):
        url = os.getenv("DISCORD_WEBHOOK_URL")
        if not url:
            return  # Skip if webhook not configured
        formatter = logging.Formatter(logging_format)
        message = formatter.format(record)
        data = {
            "content": message,
            "username": "A&O ERROR"
        }
        requests.post(url, json=data)

    def emit(self, record):
        """Send the log records (created by loggers) to
        the appropriate destination.
        """
        self.send_discord_webhook(record)
###


Markdown(app)

# Initialize database with proper defaults for existing provinces
def _init_province_defaults():
    """Ensure all provinces have proper default values for stats"""
    try:
        from database import get_db_connection
        with get_db_connection() as conn:
            db = conn.cursor()
            # Update provinces with 0 happiness/productivity to have neutral 50% defaults
            db.execute("UPDATE provinces SET happiness=50 WHERE happiness=0")
            db.execute("UPDATE provinces SET productivity=50 WHERE productivity=0")  
            db.execute("UPDATE provinces SET consumer_spending=50 WHERE consumer_spending=0")
            conn.commit()
    except Exception as e:
        print(f"Note: Province defaults initialization skipped (may be normal): {e}")

_init_province_defaults()

# register blueprints
app.register_blueprint(upgrades.bp)
app.register_blueprint(intelligence.bp)
app.register_blueprint(wars_bp)

import config  # Parse Railway environment variables

# Attempt to ensure critical tables exist at startup. This helps avoid
# import-time UndefinedTable errors in production when the DB hasn't
# been migrated yet. It's safe to call (idempotent) and failures are
# non-fatal.
try:
    if hasattr(signup, 'ensure_signup_attempts_table'):
        signup.ensure_signup_attempts_table()
except Exception as _e:
    # Don't raise here; just log to stdout so deployment logs capture it.
    print(f"Startup: could not ensure signup_attempts table: {_e}")

try:
    environment = os.getenv("ENVIRONMENT")
except (AttributeError, TypeError):
    environment = "DEV"

if environment == "PROD":
    app.secret_key = config.get_secret_key()

    handler = RequestsHandler()
    logger.addHandler(handler)
else:
    app.secret_key = config.get_secret_key()

# Import written packages
# Don't put these above app = Flask(__name__), because it will cause a circular import error


def generate_error_code():
    numbers = 20
    code = ''.join(random.choice(string.ascii_lowercase + string.digits)
                   for _ in range(numbers))
    time = int(dt.now().timestamp())
    full = f"{code}-{time}"
    return full


@app.errorhandler(404)
def page_not_found(error):
    return render_template("error.html", code=404, message="Page not found!")


@app.errorhandler(405)
def method_not_allowed(error):
    message = f"This request method is not allowed!"
    return render_template("error.html", code=405, message=message)


@app.errorhandler(500)
def invalid_server_error(error):
    error_message = "Invalid Server Error. Sorry about that."
    error_code = generate_error_code()
    logger.error(f"[ERROR! ^^^] [{error_code}] [{error}]")
    traceback.print_exc()
    return render_template("error.html", code=500, message=error_message, error_code=error_code)

# Jinja2 filter to add commas to numbers


@app.template_filter()
def commas(value):
    try:
        rounded = round(value)
        returned = "{:,}".format(rounded)
    except (TypeError, ValueError):
        returned = value
    return returned

# Jinja2 filter to calculate days old from a date string (YYYY-MM-DD format)


@app.template_filter()
def days_old(date_string):
    from datetime import datetime
    try:
        date_obj = datetime.strptime(str(date_string), "%Y-%m-%d")
        today = datetime.today()
        delta = today - date_obj
        days = delta.days
        return f"{date_string} ({days} Days Old)"
    except (ValueError, TypeError):
        return date_string

# Jinja2 filter to render province building resource strings


@app.template_filter()
def prores(unit):
    change_price = False
    unit = unit.lower()
    if "," in unit:
        split_unit = unit.split(", ")
        unit = split_unit[0]
        change_price = float(split_unit[1])

    renames = {
        "Fulfillment centers": "malls",
        "Bullet trains": "monorails"
    }

    print(unit)
    unit_name = unit.replace("_", " ").capitalize()
    if unit_name == "Coal burners":
        unit_name = "Coal power plants"
    try:
        unit = renames[unit_name]
    except KeyError:
        ...

    price = PROVINCE_UNIT_PRICES[f'{unit}_price']
    if change_price:
        price = price * change_price
    try:
        resources = ", ".join(
            [f"{i[1]} {i[0]}" for i in PROVINCE_UNIT_PRICES[f"{unit}_resource"].items()])
        full = f"{unit_name} cost { commas(price) }, { resources } each"
    except KeyError:
        full = f"{unit_name} cost { commas(price) } each"
    return full

# Jinja2 filter to render military unit resource strings


@app.template_filter()
def milres(unit):
    change_price = False
    if "," in unit:
        split_unit = unit.split(", ")
        unit = split_unit[0]
        change_price = float(split_unit[1])
    price = MILDICT[unit]['price']
    if change_price:
        price = price * change_price
    try:
        resources = ", ".join(
            [f"{i[1]} {i[0]}" for i in MILDICT[unit]["resources"].items()])
        full = f"{unit.capitalize()} cost { commas(price) }, { resources } each"
    except KeyError:
        full = f"{unit.capitalize()} cost { commas(price) } each"
    return full

# Jinja2 filter to format resource names (replace underscores with spaces)
@app.template_filter()
def formatname(value):
    """Convert snake_case to Title Case, with special handling for certain terms"""
    if not isinstance(value, str):
        return value
    
    # Special cases
    if value.lower() == "citycount":
        return "City"
    
    # Replace underscores and capitalize
    return value.replace("_", " ").title()

def get_resources():
    with get_db_cursor(cursor_factory=RealDictCursor) as db:
        cId = session["user_id"]

        try:
            db.execute(
                "SELECT * FROM resources INNER JOIN stats ON resources.id=stats.id WHERE stats.id=%s", (cId,))
            resources = dict(db.fetchone())
            return resources
        except TypeError:
            return {}


@app.context_processor
def inject_user():
    return dict(get_resources=get_resources)


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/robots.txt")
def robots():
    return send_from_directory("static", "robots.txt")


@app.route("/account", methods=["GET"])
@login_required
@cache_response(ttl_seconds=60)
def account():
    with get_db_cursor(cursor_factory=RealDictCursor) as db:

        cId = session["user_id"]

        db.execute("SELECT username, email, date FROM users WHERE id=%s", (cId,))
        user = dict(db.fetchone())

    return render_template("account.html", user=user)


@app.route("/recruitments", methods=["GET"])
@login_required
def recruitments():
    return render_template("recruitments.html")


@app.route("/businesses", methods=["GET"])
@login_required
def businesses():
    return render_template("businesses.html")


# Redirect bare /country to the user's own country page
@app.route("/country", methods=["GET"])
@login_required
def country_redirect():
    return redirect("/my_country")


"""
@login_required
@app.route("/assembly", methods=["GET"])
def assembly():
    return render_template("assembly.html")
"""


@app.route("/logout")
def logout():
    if session.get('user_id') is not None:
        session.clear()
    else:
        pass
    return redirect("/")


@app.route("/tutorial", methods=["GET"])
def tutorial():
    return render_template("tutorial.html")


@app.route("/forgot_password", methods=["GET"])
def forget_password():
    return render_template("forgot_password.html")


"""
@app.route("/statistics", methods=["GET"])
def statistics():
    return render_template("statistics.html")
"""


@app.route("/my_offers", methods=["GET"])
def myoffers():
    return render_template("my_offers.html")


@app.route("/war", methods=["GET"])
def war():
    return render_template("war.html")


@app.route("/warresult", methods=["GET"])
def warresult():
    return render_template("warresult.html")


@app.route("/mass_purchase", methods=["GET"])
@login_required
def mass_purchase():
    cId = session["user_id"]
    with get_db_cursor() as db:
        db.execute(
            "SELECT id, provinceName as name, CAST(cityCount AS INTEGER) as cityCount, land FROM provinces WHERE userId=%s ORDER BY provinceName",
            (cId,)
        )
        provinces = db.fetchall()
        
        # Convert to list of dicts for template
        province_list = []
        if provinces:
            colnames = [desc[0] for desc in db.description]
            for row in provinces:
                province_list.append(dict(zip(colnames, row)))
    
    return render_template("mass_purchase.html", provinces=province_list)


@app.route("/admin/init-database-DO-NOT-RUN-TWICE", methods=["GET"])
def admin_init_database():
    return "Database already initialized. Remove this route from app.py", 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5001))
    app.run(host='0.0.0.0', port=port, use_reloader=False)
