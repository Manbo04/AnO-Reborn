from flask import Blueprint, render_template, request, redirect, session, send_from_directory, flash, Response, current_app
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

@bp.route("/tutorial", methods=["GET"])
def tutorial():
    import variables as game_vars
    tutorial_constants = {
        "tax_per_citizen": game_vars.DEFAULT_TAX_INCOME,
        "cg_tax_multiplier": game_vars.CONSUMER_GOODS_TAX_MULTIPLIER,
        "no_energy_tax_multiplier": game_vars.NO_ENERGY_TAX_MULTIPLIER,
        "no_food_tax_multiplier": game_vars.NO_FOOD_TAX_MULTIPLIER,
        "land_tax_multiplier": game_vars.DEFAULT_LAND_TAX_MULTIPLIER,
        "province_base_cost": 8_000_000,
        "province_cost_scale": 0.16,
        "min_attack_supplies": 200,
    }
    chapters_path = os.path.join(current_app.root_path, "static", "tutorial", "chapters.json")
    with open(chapters_path, encoding="utf-8") as f:
        tutorial_chapters = json.load(f)["chapters"]
    return render_template("tutorial.html", tutorial_constants=tutorial_constants, tutorial_chapters=tutorial_chapters)

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
