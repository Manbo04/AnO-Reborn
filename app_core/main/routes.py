from flask import Blueprint, render_template, request, redirect, session, send_from_directory, flash, Response, current_app
from xml.sax.saxutils import escape
from helpers import login_required, error
from database import get_request_cursor
import os
import time as time_module
import json

bp = Blueprint('main_bp', __name__)

@bp.route("/", methods=["GET", "POST"])
def index():
    from flask import make_response
    resp = make_response(render_template("index.html"))
    return resp

@bp.route("/robots.txt")
def robots():
    return send_from_directory("static", "robots.txt")


@bp.route("/google7c77c4ff4f7be650.html")
def google_search_console_verify():
    return send_from_directory("static", "google7c77c4ff4f7be650.html")


@bp.route("/sitemap.xml")
def sitemap():
    """Public pages Google uses for sitelinks and rich results."""
    site = "https://affairsandorder.com"
    pages = [
        ("/", "daily", "1.0"),
        ("/signup", "monthly", "0.9"),
        ("/login", "monthly", "0.9"),
        ("/tutorial", "weekly", "0.8"),
        ("/mechanics", "weekly", "0.8"),
        ("/mechanics/resources", "monthly", "0.6"),
        ("/mechanics/revenue", "monthly", "0.6"),
        ("/mechanics/consumer_goods", "monthly", "0.6"),
        ("/mechanics/rations", "monthly", "0.6"),
        ("/mechanics/war", "monthly", "0.6"),
        ("/forgot_password", "yearly", "0.4"),
        ("/rankings", "daily", "0.7"),
        ("/countries", "daily", "0.7"),
    ]
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for path, changefreq, priority in pages:
        loc = escape(f"{site}{path}")
        lines.append("  <url>")
        lines.append(f"    <loc>{loc}</loc>")
        lines.append(f"    <changefreq>{changefreq}</changefreq>")
        lines.append(f"    <priority>{priority}</priority>")
        lines.append("  </url>")
    lines.append("</urlset>")
    body = "\n".join(lines)
    return Response(body, mimetype="application/xml")

@bp.route("/tutorial", methods=["GET"])
def tutorial():
    from flask import redirect, url_for
    return redirect("/provinces")

@bp.route("/dev/reset_tutorial", methods=["GET"])
@login_required
def dev_reset_tutorial():
    from database import get_request_cursor
    try:
        user_id = session["user_id"]
        with get_request_cursor() as db:
            # 1. Ensure the column exists on production!
            db.execute("ALTER TABLE stats ADD COLUMN IF NOT EXISTS tutorial_step INTEGER DEFAULT 0")
            # 2. Reset the tutorial for the user
            db.execute("UPDATE stats SET tutorial_step = 0, tutorial_chapters_claimed = '{}', tutorial_graduated_at = NULL WHERE id = %s", (user_id,))
        return "Migration applied and tutorial reset! Go to /provinces"
    except Exception as e:
        import traceback
        return f"Error: {str(e)}<br><pre>{traceback.format_exc()}</pre>"

@bp.route("/mechanics", methods=["GET"])
def mechanics(): return render_template("mechanics.html")

@bp.route("/mechanics/consumer_goods", methods=["GET"])
def mechanics_consumer_goods(): return render_template("mechanics/consumer_goods.html")

@bp.route("/mechanics/revenue", methods=["GET"])
def mechanics_revenue(): return render_template("mechanics/revenue.html")

@bp.route("/mechanics/resources", methods=["GET"])
def mechanics_resources(): return render_template("mechanics/resources.html")

@bp.route("/mechanics/rations", methods=["GET"])
def mechanics_rations(): return render_template("mechanics/rations.html")

@bp.route("/mechanics/war", methods=["GET"])
def mechanics_war(): return render_template("mechanics/war.html")

@bp.route("/flag/<flag_type>/<int:flag_id>")
def serve_flag(flag_type, flag_id):
    import base64
    from flask import Response
    from database import table_has_column

    cache_key = f"{flag_type}_{flag_id}"
    if not hasattr(serve_flag, "_cache"): serve_flag._cache = {}
    cached = serve_flag._cache.get(cache_key)
    if cached is not None:
        body, mimetype, cached_at = cached
        if time_module.time() - cached_at < 300:
            response = Response(body, mimetype=mimetype)
            response.headers["Cache-Control"] = "public, max-age=3600"
            return response
        else: del serve_flag._cache[cache_key]

    with get_request_cursor() as cur:
        row = None
        try:
            if flag_type == "country":
                if table_has_column("users", "flag_data"):
                    cur.execute("SELECT flag_data FROM users WHERE id = %s", (flag_id,))
                    row = cur.fetchone()
                if not (row and row[0]):
                    cur.execute("SELECT flag FROM users WHERE id = %s", (flag_id,))
                    fname = cur.fetchone()
                    if fname and fname[0]: return send_from_directory("static/flags", fname[0])
            elif flag_type == "coalition":
                if table_has_column("colnames", "flag_data"):
                    cur.execute("SELECT flag_data FROM colNames WHERE id = %s", (flag_id,))
                    row = cur.fetchone()
                if not (row and row[0]):
                    cur.execute("SELECT flag FROM colNames WHERE id = %s", (flag_id,))
                    fname = cur.fetchone()
                    if fname and fname[0]: return send_from_directory("static/flags", fname[0])
            else: return send_from_directory("static/flags", "default_flag.jpg")
        except Exception:
            cur.connection.rollback()
            return send_from_directory("static/flags", "default_flag.jpg")

        if row and row[0]:
            try:
                flag_data = base64.b64decode(row[0])
                if flag_data[:8] == b"\x89PNG\r\n\x1a\n": mimetype = "image/png"
                elif flag_data[:2] == b"\xff\xd8": mimetype = "image/jpeg"
                elif flag_data[:6] in (b"GIF87a", b"GIF89a"): mimetype = "image/gif"
                else: mimetype = "image/png"

                if len(serve_flag._cache) < 500: serve_flag._cache[cache_key] = (flag_data, mimetype, time_module.time())
                response = Response(flag_data, mimetype=mimetype)
                response.headers["Cache-Control"] = "public, max-age=3600"
                return response
            except Exception as e: pass

        if flag_type == "country": cur.execute("SELECT flag FROM users WHERE id = %s", (flag_id,))
        else: cur.execute("SELECT flag FROM colNames WHERE id = %s", (flag_id,))
        row = cur.fetchone()
        if row and row[0]:
            try: return send_from_directory("static/flags", row[0])
            except Exception: pass

        default_path = os.path.join(current_app.static_folder, "flags", "default_flag.jpg")
        try:
            with open(default_path, "rb") as f: default_bytes = f.read()
            if len(serve_flag._cache) < 500: serve_flag._cache[cache_key] = (default_bytes, "image/jpeg", time_module.time())
        except Exception: pass
        return send_from_directory("static/flags", "default_flag.jpg")
