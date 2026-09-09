"""Routes that serve the dynamic per-entity social preview images.

These are what a pasted /country, /coalition, or /province link actually
shows as its Discord (or Slack/iMessage/Twitter) link-embed image, via
the og:image / twitter:image tags each page sets (see templates/country.html
etc.). Kept deliberately lean — this fires on every link unfurl, which can
happen several times per link paste (Discord re-fetches periodically), so
each route does the minimum DB work plus a short in-process cache, same
pattern as app_core/main/routes.py's serve_flag.
"""

import base64
import time as time_module

from flask import Blueprint, Response, current_app

from database import (
    get_request_cursor,
    rollback_db_cursor,
    table_has_column,
    get_coalition_members_table,
)

from .card_generator import render_card

bp = Blueprint("social_cards", __name__)

_CACHE = {}
_CACHE_TTL = 600  # seconds — Discord doesn't re-fetch on every message view


def _cache_get(key):
    entry = _CACHE.get(key)
    if entry is None:
        return None
    body, at = entry
    if time_module.time() - at > _CACHE_TTL:
        del _CACHE[key]
        return None
    return body


def _cache_set(key, body):
    if len(_CACHE) > 500:
        _CACHE.clear()
    _CACHE[key] = (body, time_module.time())


def _png_response(body: bytes) -> Response:
    response = Response(body, mimetype="image/png")
    response.headers["Cache-Control"] = "public, max-age=600"
    return response


def _fetch_flag_bytes(flag_type: str, flag_id: int):
    """Best-effort flag image lookup — mirrors app_core/main/routes.py's
    serve_flag DB-blob lookup, minus its filesystem-filename fallback
    (card_generator already falls back to a bundled default flag)."""
    column_by_type = {
        "country": ("users", "flag_data"),
        "coalition": ("colnames", "flag_data"),
        "province": ("provinces", "flag_data"),
    }
    table, column = column_by_type.get(flag_type, (None, None))
    if not table:
        return None
    try:
        with get_request_cursor(read_only=True) as db:
            if not table_has_column(table, column):
                return None
            id_column = "id"
            db.execute(f"SELECT {column} FROM {table} WHERE {id_column} = %s", (flag_id,))
            row = db.fetchone()
            if row and row[0]:
                return base64.b64decode(row[0])
    except Exception:
        pass
    return None


def _fmt_num(value) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "0"


@bp.route("/social-card/country/<int:cid>.png")
def country_card(cid):
    cache_key = f"country_{cid}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return _png_response(cached)

    header = _fetch_country_header(cid)
    if header is None:
        from flask import abort

        abort(404)

    stats = [
        ("Population", _fmt_num(header["population"])),
        ("Provinces", _fmt_num(header["province_count"])),
        ("Land", _fmt_num(header["total_land"])),
    ]
    if header.get("join_number"):
        stats.append(("Nation #", _fmt_num(header["join_number"])))

    subtitle = None
    if header.get("leader_name"):
        subtitle = f"Led by {header['leader_name']}"
    elif header.get("location"):
        subtitle = f"A {header['location']} nation"

    png = render_card(
        kind_label="Nation Dossier",
        title=header["username"],
        subtitle=subtitle,
        stats=stats,
        flag_bytes=_fetch_flag_bytes("country", cid),
        accent_hex=header.get("name_color"),
        ribbon_text=(f"Coalition: {header['coalition_name']}" if header.get("coalition_name") else None),
    )
    _cache_set(cache_key, png)
    return _png_response(png)


def _fetch_country_header(cid: int):
    members_tbl = get_coalition_members_table()
    with get_request_cursor(read_only=True) as db:
        base_sql = """
            SELECT u.username, u.leader_name, s.location,
                   p.total_pop, p.province_count, p.total_land,
                   nc.value AS name_color
              FROM users u
              LEFT JOIN stats s ON s.id = u.id
              LEFT JOIN (
                  SELECT userid,
                         COALESCE(SUM(population), 0) AS total_pop,
                         COUNT(id) AS province_count,
                         COALESCE(SUM(land), 0) AS total_land
                    FROM provinces
                   WHERE userid = %s
                   GROUP BY userid
              ) p ON p.userid = u.id
              LEFT JOIN cosmetics nc
                     ON nc.id = s.equipped_name_color_cosmetic_id AND nc.is_active = TRUE
             WHERE u.id = %s
        """
        row = None
        try:
            db.execute(base_sql, (cid, cid))
            row = db.fetchone()
        except Exception:
            rollback_db_cursor(db)
        if not row:
            return None

        username, leader_name, location, total_pop, province_count, total_land, name_color = row

        coalition_name = None
        if members_tbl:
            try:
                db.execute(
                    f"""
                    SELECT c.name FROM {members_tbl} cm
                    JOIN colNames c ON c.id = cm.colid
                    WHERE cm.userid = %s
                    """,
                    (cid,),
                )
                col_row = db.fetchone()
                coalition_name = col_row[0] if col_row else None
            except Exception:
                rollback_db_cursor(db)

        join_number = None
        try:
            db.execute("SELECT join_number FROM users WHERE id = %s", (cid,))
            jn_row = db.fetchone()
            join_number = jn_row[0] if jn_row else None
        except Exception:
            rollback_db_cursor(db)

        return {
            "username": username,
            "leader_name": leader_name,
            "location": location,
            "population": total_pop or 0,
            "province_count": province_count or 0,
            "total_land": total_land or 0,
            "name_color": name_color,
            "coalition_name": coalition_name,
            "join_number": join_number,
        }


@bp.route("/social-card/coalition/<int:coalition_id>.png")
def coalition_card(coalition_id):
    cache_key = f"coalition_{coalition_id}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return _png_response(cached)

    data = _fetch_coalition_header(coalition_id)
    if data is None:
        from flask import abort

        abort(404)

    stats = [
        ("Members", _fmt_num(data["members_count"])),
        ("Population", _fmt_num(data["total_population"])),
        ("Provinces", _fmt_num(data["total_provinces"])),
    ]
    subtitle_parts = []
    if data.get("members_count"):
        subtitle_parts.append(f"{data['members_count']} member nation{'s' if data['members_count'] != 1 else ''}")
    if data.get("coalition_type"):
        subtitle_parts.append(data["coalition_type"])
    subtitle = " · ".join(subtitle_parts) if subtitle_parts else None

    png = render_card(
        kind_label="Coalition",
        title=data["name"],
        subtitle=subtitle,
        stats=stats,
        flag_bytes=_fetch_flag_bytes("coalition", coalition_id),
        accent_hex="#d4a843",  # --gold — coalitions read as the game's "guild" concept
    )
    _cache_set(cache_key, png)
    return _png_response(png)


def _fetch_coalition_header(coalition_id: int):
    members_tbl = get_coalition_members_table()
    if not members_tbl:
        return None
    with get_request_cursor(read_only=True) as db:
        try:
            db.execute(
                f"""
                SELECT c.name, c.type,
                       COUNT(DISTINCT cm.userid) AS members_count,
                       COALESCE(SUM(prov.total_pop), 0) AS total_population,
                       COALESCE(SUM(prov.total_provinces), 0) AS total_provinces
                  FROM colNames c
                  LEFT JOIN {members_tbl} cm ON c.id = cm.colid
                  LEFT JOIN (
                      SELECT userid, SUM(population) AS total_pop, COUNT(id) AS total_provinces
                        FROM provinces
                       GROUP BY userid
                  ) prov ON prov.userid = cm.userid
                 WHERE c.id = %s
                 GROUP BY c.id, c.name, c.type
                """,
                (coalition_id,),
            )
            row = db.fetchone()
        except Exception:
            rollback_db_cursor(db)
            row = None
        if not row:
            return None
        name, coalition_type, members_count, total_population, total_provinces = row
        return {
            "name": name,
            "coalition_type": coalition_type,
            "members_count": members_count or 0,
            "total_population": total_population or 0,
            "total_provinces": total_provinces or 0,
        }


@bp.route("/social-card/province/<int:province_id>.png")
def province_card(province_id):
    cache_key = f"province_{province_id}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return _png_response(cached)

    data = _fetch_province_header(province_id)
    if data is None:
        from flask import abort

        abort(404)

    stats = [
        ("Population", _fmt_num(data["population"])),
        ("Land", _fmt_num(data["land"])),
        ("Cities", _fmt_num(data["citycount"])),
    ]
    if data.get("happiness") is not None:
        stats.append(("Happiness", f"{int(data['happiness'])}%"))

    subtitle = f"Province of {data['owner_username']}" if data.get("owner_username") else None
    if data.get("is_capital") and data.get("owner_username"):
        subtitle = f"Capital province of {data['owner_username']}"

    png = render_card(
        kind_label="Province",
        title=data["name"],
        subtitle=subtitle,
        stats=stats,
        flag_bytes=_fetch_flag_bytes("province", province_id),
        accent_hex="#2d9f6f",  # --success — provinces read as the "growth" unit of the game
    )
    _cache_set(cache_key, png)
    return _png_response(png)


def _fetch_province_header(province_id: int):
    with get_request_cursor(read_only=True) as db:
        try:
            db.execute(
                """
                SELECT p.provinceName, p.population, p.land,
                       CAST(p.citycount AS INTEGER), p.happiness, p.is_capital,
                       u.username
                  FROM provinces p
                  LEFT JOIN users u ON u.id = p.userId
                 WHERE p.id = %s
                """,
                (province_id,),
            )
            row = db.fetchone()
        except Exception:
            rollback_db_cursor(db)
            row = None
        if not row:
            return None
        name, population, land, citycount, happiness, is_capital, owner_username = row
        return {
            "name": name,
            "population": population or 0,
            "land": land or 0,
            "citycount": citycount or 0,
            "happiness": happiness,
            "is_capital": bool(is_capital),
            "owner_username": owner_username,
        }
