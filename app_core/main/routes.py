from flask import Blueprint, render_template, request, redirect, session, send_from_directory, flash, Response, current_app, jsonify
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

    if session.get("user_id"):
        return make_response(render_template("hub.html", **_hub_context()))

    resp = make_response(render_template("index.html"))
    return resp


def _hub_context():
    from app_core.chat import repositories as chat_repo
    from app_core.community import repositories as community_repo

    user_id = session["user_id"]
    with get_request_cursor() as db:
        db.execute("SELECT username FROM users WHERE id=%s", (user_id,))
        row = db.fetchone()
        username = row[0] if row else None

        db.execute(
            "SELECT COUNT(*) FROM users WHERE last_active > now() - interval '5 minutes'"
        )
        nations_online = db.fetchone()[0]

        db.execute("SELECT COUNT(*) FROM users")
        total_nations = db.fetchone()[0]

        db.execute("SELECT COUNT(*) FROM wars WHERE peace_date IS NULL")
        wars_now = db.fetchone()[0]

        db.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT created_at FROM coalition_messages WHERE created_at > now() - interval '24 hours'
                UNION ALL
                SELECT created_at FROM direct_messages WHERE created_at > now() - interval '24 hours'
                UNION ALL
                SELECT created_at FROM global_chat_messages WHERE created_at > now() - interval '24 hours'
            ) recent_messages
            """
        )
        messages_today = db.fetchone()[0]

        # Each item carries a real flag image (the relevant nation's, via
        # /flag/country/<id>) instead of the reference mockup's invented
        # stock photos -- there's no per-story photo in this game, but a
        # real flag is a genuine, always-available image, not a placeholder.
        news = []
        db.execute("SELECT id, username FROM users ORDER BY id DESC LIMIT 3")
        for uid, name in db.fetchall():
            news.append({
                "flag_user_id": uid,
                "title": f"New nation: {name}",
                "snippet": "A new nation has risen to power in Terra.",
                "href": f"/country/id={uid}",
            })

        db.execute(
            """
            SELECT wars.id, u1.id, u1.username, u2.username
            FROM wars
            JOIN users u1 ON wars.attacker = u1.id
            JOIN users u2 ON wars.defender = u2.id
            WHERE wars.peace_date IS NULL
            ORDER BY wars.id DESC LIMIT 3
            """
        )
        for war_id, attacker_id, att, defn in db.fetchall():
            news.append({
                "flag_user_id": attacker_id,
                "title": f"{att} declared war on {defn}",
                "snippet": "A new conflict has begun.",
                "href": f"/war/{war_id}",
            })

        db.execute(
            """
            SELECT u.id, u.username, td.name
            FROM user_tech ut
            JOIN tech_dictionary td ON ut.tech_id = td.tech_id
            JOIN users u ON ut.user_id = u.id
            ORDER BY ut.user_id DESC LIMIT 3
            """
        )
        for uid, name, tech in db.fetchall():
            tech_name = str(tech).replace("_", " ").title()
            news.append({
                "flag_user_id": uid,
                "title": f"{name} researched {tech_name}",
                "snippet": "A new technology has been unlocked.",
                "href": f"/country/id={uid}",
            })

        chat_history = chat_repo.list_global_chat_messages()
        online_sender_ids = []
        for m in chat_history:
            sid = m["sender_id"]
            if sid not in online_sender_ids:
                online_sender_ids.append(sid)
            if len(online_sender_ids) >= 4:
                break

    return dict(
        username=username,
        nations_online=nations_online,
        total_nations=total_nations,
        wars_now=wars_now,
        messages_today=messages_today,
        news=news,
        chat_history=chat_history,
        online_sender_ids=online_sender_ids,
        recent_threads=community_repo.list_threads(limit=4),
        recent_devlog=community_repo.list_devlog_entries(limit=3),
    )


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
        ("/mechanics/biomes", "monthly", "0.6"),
        ("/mechanics/revenue", "monthly", "0.6"),
        ("/mechanics/consumer_goods", "monthly", "0.6"),
        ("/mechanics/rations", "monthly", "0.6"),
        ("/mechanics/war", "monthly", "0.6"),
        ("/privacy", "yearly", "0.3"),
        ("/terms", "yearly", "0.3"),
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

_TUTORIAL_CHAPTERS_CACHE: list | None = None


def _load_tutorial_chapters() -> list:
    """Chapter metadata for tutorial.html (video stems, posters, follow links).

    tutorial.html indexes tutorial_chapters[0..9], so this always returns a
    10-entry list — padded with inert placeholders if chapters.json is short
    or unreadable — so the page can never 500 on missing metadata.
    """
    global _TUTORIAL_CHAPTERS_CACHE
    if _TUTORIAL_CHAPTERS_CACHE is None:
        import json
        import os

        from flask import current_app

        chapters: list = []
        try:
            path = os.path.join(
                current_app.static_folder, "tutorial", "chapters.json"
            )
            with open(path, encoding="utf-8") as f:
                chapters = json.load(f).get("chapters", []) or []
        except Exception:
            chapters = []
        while len(chapters) < 10:
            chapters.append(
                {
                    "stem": "ch00-missing",
                    "title": "Tutorial chapter",
                    "poster": "images/province.jpg",
                    "aria_label": "Tutorial chapter",
                    "follow_links": [],
                }
            )
        _TUTORIAL_CHAPTERS_CACHE = chapters
    return _TUTORIAL_CHAPTERS_CACHE


@bp.route("/tutorial", methods=["GET"])
def tutorial():
    # Values mirror static/tutorial.js fallbacks; the quiz answers reference
    # them, so keep the two places in sync if game balance changes.
    tutorial_constants = {
        "tax_per_citizen": 0.75,
        "min_attack_supplies": 200,
    }
    return render_template(
        "tutorial.html",
        tutorial_chapters=_load_tutorial_chapters(),
        tutorial_constants=tutorial_constants,
    )

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

@bp.route("/privacy", methods=["GET"])
def privacy_policy(): return render_template("privacy_policy.html")

@bp.route("/terms", methods=["GET"])
def terms_of_service(): return render_template("terms_of_service.html")

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

@bp.route("/mechanics/biomes", methods=["GET"])
def mechanics_biomes():
    import game_ui
    from app_core.economy.biome_buildings import (
        ALL_MINE_BUILDINGS,
        MINE_INFO,
        mines_for_biome,
    )

    def mine_badge(mine_name):
        return {
            "name": mine_name,
            "display_name": MINE_INFO[mine_name]["display_name"],
            "resource": MINE_INFO[mine_name]["resource"],
            "icon": game_ui.BUILDING_VISUAL_ICONS.get(mine_name, "domain"),
        }

    biomes = []
    for biome in game_ui.nation_biome_choices():
        allowed = mines_for_biome(biome["value"])
        biomes.append({**biome, "mines": [mine_badge(m) for m in allowed]})

    all_mines = [mine_badge(m) for m in ALL_MINE_BUILDINGS]
    matrix = [
        {
            "biome": biome["label"],
            "allowed": set(mines_for_biome(biome["value"])),
        }
        for biome in game_ui.nation_biome_choices()
    ]

    return render_template(
        "mechanics/biomes.html",
        biomes=biomes,
        all_mines=all_mines,
        matrix=matrix,
    )

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


@bp.route("/api/quick_search")
@login_required
def api_quick_search():
    """Instant nation+coalition search for the redesigned UI's topbar dropdown
    (see /Users/dede/ano-redesign/plan/PRODUCTION_PORT_PLAN.md §6.1). Distinct
    from /countries' and /coalitions' own full server-side search+pagination —
    this is a small, cheap, capped lookup for a type-ahead box, not a results
    page. Reuses the existing /flag/<type>/<id> route for flag images rather
    than doing an expensive per-row flag lookup here.
    """
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify({"nations": [], "coalitions": []})

    like = f"%{q}%"
    nations = []
    coalitions = []
    with get_request_cursor(read_only=True) as cur:
        try:
            if q.isdigit():
                cur.execute(
                    "SELECT id, username FROM users WHERE id = %s LIMIT 5",
                    (int(q),),
                )
            else:
                cur.execute(
                    "SELECT id, username FROM users WHERE username ILIKE %s ORDER BY username LIMIT 5",
                    (like,),
                )
            nations = [{"id": r[0], "name": r[1], "flag_url": f"/flag/country/{r[0]}"} for r in cur.fetchall()]
        except Exception:
            cur.connection.rollback()
            nations = []

        try:
            if q.isdigit():
                cur.execute(
                    "SELECT id, name FROM colNames WHERE id = %s LIMIT 5",
                    (int(q),),
                )
            else:
                cur.execute(
                    "SELECT id, name FROM colNames WHERE name ILIKE %s ORDER BY name LIMIT 5",
                    (like,),
                )
            coalitions = [{"id": r[0], "name": r[1], "flag_url": f"/flag/coalition/{r[0]}"} for r in cur.fetchall()]
        except Exception:
            cur.connection.rollback()
            coalitions = []

    return jsonify({"nations": nations, "coalitions": coalitions})


@bp.route("/api/notifications")
@login_required
def api_notifications():
    """Real personal notifications for the redesigned UI's topbar bell (see
    /Users/dede/ano-redesign/plan/PRODUCTION_PORT_PLAN.md §6.1). Reads the
    same 'news' table country.html's own Reports & News section already
    reads/dismisses from (news.destination_id) -- this is just a second,
    lightweight view onto the same real data, not a new notification system.
    """
    from datetime import date as _date

    user_id = session["user_id"]
    items = []
    with get_request_cursor(read_only=True) as cur:
        try:
            cur.execute(
                "SELECT id, message, date FROM news WHERE destination_id=%s ORDER BY id DESC LIMIT 6",
                (user_id,),
            )
            today = _date.today()
            for row_id, message, day in cur.fetchall():
                if day is None:
                    when = ""
                else:
                    days_old = (today - day).days
                    when = "Today" if days_old <= 0 else ("Yesterday" if days_old == 1 else f"{days_old}d ago")
                items.append({"id": row_id, "message": message, "when": when})
        except Exception:
            cur.connection.rollback()
            items = []

    return jsonify({"items": items})
