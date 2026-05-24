"""Authenticated HTTP API for the AnO Discord bot (internal use only)."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

from database import (
    UserQueries,
    assign_discord_id_to_user,
    discord_link_codes_table_exists,
    get_coalition_members_table,
    get_user_full_data,
    resolve_user_id_by_discord,
    users_table_has_column,
    QueryHelper,
)
from helpers import get_influence

bp = Blueprint("bot_api", __name__)

CODE_TTL_MINUTES = int(os.getenv("DISCORD_LINK_CODE_TTL_MINUTES", "30"))
CODE_LENGTH = 8
SNAPSHOT_CACHE_TTL_SECONDS = int(os.getenv("BOT_NATION_SNAPSHOT_CACHE_SECONDS", "90"))
_snapshot_cache: Dict[int, Tuple[float, Dict[str, Any]]] = {}


def _bot_secret() -> Optional[str]:
    explicit = (os.getenv("BOT_API_SECRET") or "").strip()
    if explicit:
        return explicit
    if os.getenv("RAILWAY_ENVIRONMENT_NAME") or os.getenv("ENVIRONMENT") == "PROD":
        return None
    secret_key = (os.getenv("SECRET_KEY") or "").strip()
    if secret_key:
        return hashlib.sha256(f"ano-bot-api-v1:{secret_key}".encode()).hexdigest()
    return None


def _require_bot_secret() -> Optional[Tuple[Any, int]]:
  secret = _bot_secret()
  if not secret:
    return jsonify({"error": "Bot API not configured"}), 503
  header = request.headers.get("X-Bot-Secret") or ""
  if not hmac.compare_digest(header, secret):
    return jsonify({"error": "Forbidden"}), 403
  return None


def _discord_user_id_from_request() -> Optional[str]:
  return (request.headers.get("X-Discord-User-Id") or "").strip() or None


def _resolve_nation_identifier(identifier: str) -> Optional[str]:
  if not identifier or not str(identifier).strip():
    return None
  raw = str(identifier).strip()
  if raw.isdigit():
    row = QueryHelper.fetch_one(
      "SELECT id FROM users WHERE id::text = %s", (raw,)
    )
    if row:
        return str(row[0])
  row = QueryHelper.fetch_one(
      "SELECT id FROM users WHERE LOWER(username) = LOWER(%s) LIMIT 1",
      (raw,),
  )
  return str(row[0]) if row else None


_wars_schema_cache: Optional[Dict[str, Optional[str]]] = None


def _wars_schema() -> Dict[str, Optional[str]]:
    """Detect wars table column names (legacy id/attacker/defender vs normalized)."""
    global _wars_schema_cache
    if _wars_schema_cache is not None:
        return _wars_schema_cache
    cols: set = set()
    try:
        rows = QueryHelper.fetch_all(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'wars'
            """
        )
        cols = {(r[0] or "").lower() for r in rows or []}
    except Exception as exc:
        logger.warning("wars schema detection failed: %s", exc)
    _wars_schema_cache = {
        "war_pk": "war_id" if "war_id" in cols else "id" if "id" in cols else None,
        "attacker": (
            "attacker_id"
            if "attacker_id" in cols
            else "attacker"
            if "attacker" in cols
            else None
        ),
        "defender": (
            "defender_id"
            if "defender_id" in cols
            else "defender"
            if "defender" in cols
            else None
        ),
    }
    return _wars_schema_cache


def _empty_coalition() -> Dict[str, Any]:
    return {
        "coalition_id": None,
        "coalition_name": None,
        "role": None,
        "tax_rate": 0,
    }


def _coalition_from_row(row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not row:
        return _empty_coalition()
    return {
        "coalition_id": row.get("colid"),
        "coalition_name": row.get("name"),
        "role": row.get("role"),
        "tax_rate": int(row.get("tax_rate") or 0),
    }


def _coalition_summary(user_id: int, db=None) -> Dict[str, Any]:
    members_tbl = get_coalition_members_table()
    if not members_tbl:
        return _empty_coalition()
    query = f"""
        SELECT cm.colid, cm.role, c.name, COALESCE(c.tax_rate, 0) AS tax_rate
        FROM {members_tbl} cm
        LEFT JOIN colNames c ON c.id = cm.colid
        WHERE cm.userid = %s
    """
    if db is not None:
        db.execute(query, (user_id,))
        row = db.fetchone()
        return _coalition_from_row(dict(row) if row else None)
    row = QueryHelper.fetch_one(query, (user_id,), dict_cursor=True)
    return _coalition_from_row(row)


def _active_war_count(user_id: int) -> int:
    schema = _wars_schema()
    atk, dfn = schema.get("attacker"), schema.get("defender")
    if not atk or not dfn:
        return 0
    row = QueryHelper.fetch_one(
        f"""
        SELECT COUNT(*) FROM wars
        WHERE peace_date IS NULL
          AND ({atk} = %s OR {dfn} = %s)
        """,
        (user_id, user_id),
    )
    return int(row[0]) if row else 0


def _rows_to_active_wars(user_id: int, rows: List[Any]) -> List[Dict[str, Any]]:
    wars: List[Dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        attacker_id = row["attacker_id"]
        defender_id = row["defender_id"]
        if user_id == attacker_id:
            opponent_id = defender_id
            opponent_name = row["defender_name"]
            side = "attacker"
        else:
            opponent_id = attacker_id
            opponent_name = row["attacker_name"]
            side = "defender"
        wars.append(
            {
                "war_id": row["war_id"],
                "side": side,
                "war_type": row.get("war_type"),
                "opponent_id": opponent_id,
                "opponent_name": opponent_name,
            }
        )
    return wars


def _list_active_wars(user_id: int, db=None) -> List[Dict[str, Any]]:
    schema = _wars_schema()
    war_pk, atk, dfn = schema.get("war_pk"), schema.get("attacker"), schema.get("defender")
    if not war_pk or not atk or not dfn:
        return []
    query = f"""
        SELECT w.{war_pk} AS war_id, w.{atk} AS attacker_id, w.{dfn} AS defender_id,
               w.war_type,
               ua.username AS attacker_name, ud.username AS defender_name
        FROM wars w
        JOIN users ua ON ua.id = w.{atk}
        JOIN users ud ON ud.id = w.{dfn}
        WHERE w.peace_date IS NULL
          AND (w.{atk} = %s OR w.{dfn} = %s)
        ORDER BY w.{war_pk} DESC
        LIMIT 12
    """
    if db is not None:
        db.execute(query, (user_id, user_id))
        rows = [dict(r) for r in db.fetchall() or []]
        return _rows_to_active_wars(user_id, rows)
    rows = QueryHelper.fetch_all(query, (user_id, user_id), dict_cursor=True)
    return _rows_to_active_wars(user_id, rows or [])


def warmup_bot_api() -> None:
    """Preload schema detection so first slash command is not slow."""
    _wars_schema()


def _snapshot_cache_get(user_id: int) -> Optional[Dict[str, Any]]:
    entry = _snapshot_cache.get(user_id)
    if not entry:
        return None
    expires_at, data = entry
    if time.monotonic() > expires_at:
        _snapshot_cache.pop(user_id, None)
        return None
    return data


def _snapshot_cache_set(user_id: int, data: Dict[str, Any]) -> None:
    if len(_snapshot_cache) > 800:
        _snapshot_cache.clear()
    _snapshot_cache[user_id] = (
        time.monotonic() + SNAPSHOT_CACHE_TTL_SECONDS,
        data,
    )


def _fetch_nation_snapshot_combined(user_id: int) -> Dict[str, Any]:
    """One DB connection, few queries — avoids 10+ round trips for Discord."""
    from psycopg2.extras import RealDictCursor

    from database import get_db_cursor, users_table_has_column

    started = time.perf_counter()
    extra_user_cols: List[str] = []
    if users_table_has_column("join_number"):
        extra_user_cols.append("u.join_number")
    if users_table_has_column("last_active"):
        extra_user_cols.append("u.last_active")
    extra_sql = (", " + ", ".join(extra_user_cols)) if extra_user_cols else ""

    with get_db_cursor(cursor_factory=RealDictCursor) as db:
        db.execute(
            f"""
            SELECT u.id, u.username, u.date AS date_joined{extra_sql},
                   s.location, s.gold, s.manpower, s.default_defense,
                   prov.province_count, prov.total_population, prov.total_land,
                   prov.total_cities, prov.avg_happiness, prov.avg_productivity
            FROM users u
            LEFT JOIN stats s ON s.id = u.id
            LEFT JOIN (
                SELECT userid AS uid,
                       COUNT(id) AS province_count,
                       COALESCE(SUM(population), 0) AS total_population,
                       COALESCE(SUM(land), 0) AS total_land,
                       COALESCE(SUM(citycount), 0) AS total_cities,
                       COALESCE(AVG(happiness), 0) AS avg_happiness,
                       COALESCE(AVG(productivity), 0) AS avg_productivity
                FROM provinces
                WHERE userid = %s
                GROUP BY userid
            ) prov ON prov.uid = u.id
            WHERE u.id = %s
            """,
            (user_id, user_id),
        )
        base = db.fetchone()
        if not base:
            return {}

        db.execute(
            """
            SELECT rd.name, ue.quantity::bigint AS quantity
            FROM user_economy ue
            INNER JOIN resource_dictionary rd ON rd.resource_id = ue.resource_id
            WHERE ue.user_id = %s AND ue.quantity > 0 AND rd.is_active = TRUE
            ORDER BY ue.quantity DESC
            LIMIT 24
            """,
            (user_id,),
        )
        resources = {
            r["name"]: int(r["quantity"]) for r in db.fetchall() or []
        }

        db.execute(
            """
            SELECT ud.name, um.quantity::bigint AS quantity
            FROM user_military um
            INNER JOIN unit_dictionary ud ON ud.unit_id = um.unit_id
            WHERE um.user_id = %s AND um.quantity > 0 AND ud.is_active = TRUE
            """,
            (user_id,),
        )
        military = {r["name"]: int(r["quantity"]) for r in db.fetchall() or []}
        military["manpower"] = int(base.get("manpower") or 0)
        military["default_defense"] = base.get("default_defense") or ""

        coalition = _coalition_summary(user_id, db=db)
        wars = _list_active_wars(user_id, db=db)
        influence = int(get_influence(user_id, db=db) or 0)

    province_count = int(base.get("province_count") or 0)
    snap: Dict[str, Any] = {
        "id": base["id"],
        "username": base["username"],
        "location": base.get("location"),
        "gold": int(base.get("gold") or 0),
        "influence": influence,
        "coalition": coalition,
        "active_wars": len(wars),
        "active_wars_list": wars,
        "province_count": province_count,
        "provinces": {
            "province_count": province_count,
            "total_population": int(base.get("total_population") or 0),
            "total_land": int(base.get("total_land") or 0),
            "total_cities": int(base.get("total_cities") or 0),
            "avg_happiness": float(base.get("avg_happiness") or 0),
            "avg_productivity": float(base.get("avg_productivity") or 0),
        },
        "military": military,
        "resources": resources,
    }
    if base.get("date_joined"):
        snap["date_joined"] = str(base["date_joined"])
    if base.get("join_number") is not None:
        snap["join_number"] = int(base["join_number"])
    if base.get("last_active") is not None:
        la = base["last_active"]
        snap["last_active"] = (
            la.strftime("%Y-%m-%d %H:%M UTC")
            if hasattr(la, "strftime")
            else str(la)
        )

    elapsed = time.perf_counter() - started
    if elapsed > 2.0:
        logger.warning(
            "nation snapshot slow user_id=%s took %.2fs (combined path)",
            user_id,
            elapsed,
        )
    return snap


def _province_count(user_id: int) -> int:
    try:
        row = QueryHelper.fetch_one(
            """
            SELECT COUNT(id) AS province_count
            FROM provinces
            WHERE userid = %s
            """,
            (user_id,),
            dict_cursor=True,
        )
        if row and row.get("province_count") is not None:
            return int(row["province_count"])
    except Exception as exc:
        logger.warning("province count query failed for user %s: %s", user_id, exc)
    try:
        data = get_user_full_data(user_id)
        return int((data.get("provinces") or {}).get("province_count") or 0)
    except Exception:
        return 0


def _user_account_meta(user_id: int) -> Dict[str, Any]:
    """Optional users columns for Discord display."""
    from database import users_table_has_column

    cols = ["date"]
    if users_table_has_column("join_number"):
        cols.append("join_number")
    if users_table_has_column("last_active"):
        cols.append("last_active")
    row = QueryHelper.fetch_one(
        f"SELECT {', '.join(cols)} FROM users WHERE id = %s",
        (user_id,),
        dict_cursor=True,
    )
    meta: Dict[str, Any] = {}
    if not row:
        return meta
    if row.get("date"):
        meta["date_joined"] = str(row["date"])
    if row.get("join_number") is not None:
        meta["join_number"] = int(row["join_number"])
    if row.get("last_active") is not None:
        la = row["last_active"]
        meta["last_active"] = (
            la.strftime("%Y-%m-%d %H:%M UTC")
            if hasattr(la, "strftime")
            else str(la)
        )
    return meta


def _enrich_nation_snapshot(snap: Dict[str, Any], user_id: int) -> None:
    """Add Locutus-style detail: provinces, military, resources (mutates snap)."""
    from database import ProvinceQueries

    try:
        prov = ProvinceQueries.get_user_provinces_summary(user_id)
        if prov:
            snap["provinces"] = {
                "province_count": int(prov.get("province_count") or snap.get("province_count") or 0),
                "total_population": int(prov.get("total_population") or 0),
                "total_land": int(prov.get("total_land") or 0),
                "total_cities": int(prov.get("total_cities") or 0),
                "avg_happiness": float(prov.get("avg_happiness") or 0),
                "avg_productivity": float(prov.get("avg_productivity") or 0),
            }
            snap["province_count"] = snap["provinces"]["province_count"]
    except Exception as exc:
        logger.warning("province summary failed for user %s: %s", user_id, exc)
        snap.setdefault("provinces", {})

    try:
        snap["military"] = UserQueries.get_user_military(user_id) or {}
    except Exception as exc:
        logger.warning("military snapshot failed for user %s: %s", user_id, exc)
        snap.setdefault("military", {})

    try:
        resources = UserQueries.get_user_resources(user_id)
        top = sorted(resources.items(), key=lambda x: x[1], reverse=True)
        snap["resources"] = {k: int(v) for k, v in top if int(v or 0) > 0}
    except Exception as exc:
        logger.warning("resources snapshot failed for user %s: %s", user_id, exc)
        snap.setdefault("resources", {})

    try:
        snap.update(_user_account_meta(user_id))
    except Exception as exc:
        logger.warning("user meta failed for user %s: %s", user_id, exc)


def _nation_snapshot(user_id: int, include_resources: bool = False) -> Dict[str, Any]:
    row = QueryHelper.fetch_one(
        "SELECT id, username FROM users WHERE id = %s",
        (user_id,),
        dict_cursor=True,
    )
    if not row:
        return {}

    stats_row = QueryHelper.fetch_one(
        "SELECT location, gold FROM stats WHERE id = %s",
        (user_id,),
        dict_cursor=True,
    ) or {}

    try:
        influence = int(get_influence(user_id) or 0)
    except Exception as exc:
        logger.warning("get_influence failed for user %s: %s", user_id, exc)
        influence = 0

    try:
        coalition = _coalition_summary(user_id)
    except Exception as exc:
        logger.warning("coalition summary failed for user %s: %s", user_id, exc)
        coalition = {"coalition_id": None, "coalition_name": None, "role": None}

    try:
        active_wars = _active_war_count(user_id)
    except Exception as exc:
        logger.warning("active war count failed for user %s: %s", user_id, exc)
        active_wars = 0

    snapshot: Dict[str, Any] = {
        "id": row["id"],
        "username": row["username"],
        "location": stats_row.get("location"),
        "gold": int(stats_row.get("gold") or 0),
        "influence": influence,
        "coalition": coalition,
        "active_wars": active_wars,
        "province_count": _province_count(user_id),
    }
    if include_resources:
        try:
            resources = UserQueries.get_user_resources(user_id)
            top = sorted(resources.items(), key=lambda x: x[1], reverse=True)[:12]
            snapshot["resources"] = {k: v for k, v in top if v > 0}
        except Exception as exc:
            logger.warning("resources snapshot failed for user %s: %s", user_id, exc)
            snapshot["resources"] = {}
    return snapshot


def nation_snapshot_for_bot(
    user_id: int,
    *,
    include_resources: bool = False,
    full_detail: bool = True,
) -> Dict[str, Any]:
    """Nation stats for Discord / API; never raises — returns partial data on errors."""
    try:
        if full_detail:
            cached = _snapshot_cache_get(user_id)
            if cached is not None:
                return cached
            snap = _fetch_nation_snapshot_combined(user_id)
            if snap:
                _snapshot_cache_set(user_id, snap)
            return snap

        snap = _nation_snapshot(
            user_id, include_resources=include_resources
        )
        if not snap:
            return {}
        try:
            snap["active_wars_list"] = _list_active_wars(user_id)
            snap["active_wars"] = len(snap["active_wars_list"])
        except Exception as exc:
            logger.warning("war list failed for user %s: %s", user_id, exc)
            snap["active_wars_list"] = []
        return snap
    except Exception as exc:
        logger.exception("nation_snapshot_for_bot failed for user %s: %s", user_id, exc)
        return {}


def create_discord_link_code(user_id: int) -> str:
  """Create a single-use link code for Discord /register."""
  if not discord_link_codes_table_exists():
    raise RuntimeError(
        "discord_link_codes table missing; run scripts/apply_discord_bot_migration.py"
    )
  code = secrets.token_hex(CODE_LENGTH // 2).upper()[:CODE_LENGTH]
  expires = datetime.now(timezone.utc) + timedelta(minutes=CODE_TTL_MINUTES)
  from database import get_db_cursor

  with get_db_cursor() as db:
    db.execute(
        "DELETE FROM discord_link_codes WHERE user_id = %s AND used_at IS NULL",
        (user_id,),
    )
    db.execute(
        """
        INSERT INTO discord_link_codes (code, user_id, expires_at)
        VALUES (%s, %s, %s)
        """,
        (code, user_id, expires),
    )
  return code


def get_active_discord_link_code(user_id: int) -> Optional[Dict[str, Any]]:
    """Return the newest unused, unexpired link code for this user, if any."""
    if not discord_link_codes_table_exists():
        return None
    from database import get_db_cursor

    with get_db_cursor() as db:
        db.execute(
            """
            SELECT code, expires_at
            FROM discord_link_codes
            WHERE user_id = %s
              AND used_at IS NULL
              AND expires_at > NOW()
            ORDER BY expires_at DESC
            LIMIT 1
            """,
            (user_id,),
        )
        row = db.fetchone()
    if not row:
        return None
    code, expires_at = row[0], row[1]
    return {"code": str(code), "expires_at": expires_at}


def register_discord_with_code(discord_user_id: str, code: str) -> Tuple[bool, str, Optional[int]]:
  """Validate code and link Discord to nation. Returns (ok, message, user_id)."""
  if not discord_link_codes_table_exists():
    return False, "Discord bot registration is not available yet.", None
  if not users_table_has_column("discord_id"):
    return False, "Discord linking is not enabled on this server.", None

  code_norm = (code or "").strip().upper()
  if not code_norm:
    return False, "A link code is required.", None

  from database import get_db_cursor

  with get_db_cursor() as db:
    db.execute(
        """
        SELECT user_id, expires_at, used_at
        FROM discord_link_codes
        WHERE code = %s
        """,
        (code_norm,),
    )
    row = db.fetchone()
    if not row:
      return False, "Invalid or expired link code.", None
    user_id, expires_at, used_at = row[0], row[1], row[2]
    if used_at is not None:
      return False, "This link code was already used.", None
    now = datetime.now(timezone.utc)
    if expires_at.tzinfo is None:
      expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < now:
      return False, "This link code has expired. Generate a new one on your account page.", None

    existing = resolve_user_id_by_discord(discord_user_id)
    if existing is not None and existing != user_id:
      return (
          False,
          "This Discord account is already linked to another nation.",
          None,
      )

    assign_discord_id_to_user(user_id, discord_user_id)
    db.execute(
        "UPDATE discord_link_codes SET used_at = NOW() WHERE code = %s",
        (code_norm,),
    )
  return True, "Nation linked successfully.", user_id


def _embed_to_dict(embed) -> Dict[str, Any]:
    data = embed.to_dict()
    color = data.get("color")
    if color is not None and color < 0:
        data["color"] = color & 0xFFFFFF
    return data


@bp.route("/api/bot/embed_version", methods=["GET"])
def bot_embed_version():
    """Public check that web deploy includes latest Discord embed UI."""
    from discord_bot.embeds import EMBED_UI_VERSION

    return jsonify(
        {
            "embed_ui": EMBED_UI_VERSION,
            "ok": True,
        }
    )


@bp.route("/api/bot/me_embed", methods=["GET"])
def bot_me_embed():
    err = _require_bot_secret()
    if err:
        return err
    from discord_bot.embeds import EMBED_UI_VERSION, build_nation_embed

    discord_user_id = _discord_user_id_from_request()
    if not discord_user_id:
        return jsonify({"error": "X-Discord-User-Id header required"}), 400
    user_id = resolve_user_id_by_discord(discord_user_id)
    if user_id is None:
        return jsonify(
            {"error": "Not registered. Link your nation with /register on Discord."}
        ), 404
    snap = nation_snapshot_for_bot(user_id)
    if not snap.get("id"):
        return jsonify({"error": "Could not load nation statistics."}), 500
    title = (request.args.get("title") or "Your nation").strip() or "Your nation"
    embed = build_nation_embed(snap, title)
    return jsonify({"embed": _embed_to_dict(embed), "embed_ui": EMBED_UI_VERSION})


@bp.route("/api/bot/nation_embed", methods=["GET"])
def bot_nation_embed():
    err = _require_bot_secret()
    if err:
        return err
    from discord_bot.embeds import EMBED_UI_VERSION, build_nation_embed

    identifier = request.args.get("identifier", "").strip()
    user_id = _resolve_nation_identifier(identifier)
    if user_id is None:
        return jsonify({"error": "Nation not found"}), 404
    snap = nation_snapshot_for_bot(user_id, full_detail=True)
    if not snap.get("id"):
        return jsonify({"error": "Could not load nation statistics."}), 500
    title = (request.args.get("title") or "Nation lookup").strip() or "Nation lookup"
    embed = build_nation_embed(snap, title)
    return jsonify({"embed": _embed_to_dict(embed), "embed_ui": EMBED_UI_VERSION})


@bp.route("/api/bot/health", methods=["GET"])
def bot_health():
    err = _require_bot_secret()
    if err:
        return err
    import subprocess

    sha = os.getenv("RAILWAY_GIT_COMMIT_SHA") or os.getenv("GIT_COMMIT") or "unknown"
    try:
        sha = (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                stderr=subprocess.DEVNULL,
                timeout=2,
            )
            .decode()
            .strip()
        )
    except Exception:
        pass
    return jsonify({"ok": True, "commit": sha, "discord_tables": discord_link_codes_table_exists()})


@bp.route("/api/bot/register", methods=["POST"])
def bot_register():
  err = _require_bot_secret()
  if err:
    return err
  payload = request.get_json(silent=True) or {}
  discord_user_id = str(payload.get("discord_user_id") or "").strip()
  code = str(payload.get("code") or "").strip()
  if not discord_user_id:
    return jsonify({"error": "discord_user_id is required"}), 400
  ok, message, user_id = register_discord_with_code(discord_user_id, code)
  if not ok:
    return jsonify({"error": message}), 400
  username = None
  if user_id:
    urow = QueryHelper.fetch_one(
        "SELECT username FROM users WHERE id = %s",
        (user_id,),
        dict_cursor=True,
    )
    if urow:
      username = urow.get("username")
  return jsonify(
      {"ok": True, "message": message, "user_id": user_id, "username": username}
  )


@bp.route("/api/bot/me", methods=["GET"])
def bot_me():
  err = _require_bot_secret()
  if err:
    return err
  discord_user_id = _discord_user_id_from_request()
  if not discord_user_id:
    return jsonify({"error": "X-Discord-User-Id header required"}), 400
  user_id = resolve_user_id_by_discord(discord_user_id)
  if user_id is None:
    return jsonify(
        {"error": "Not registered. Link your nation with /register on Discord."}
    ), 404
  snap = nation_snapshot_for_bot(user_id)
  if not snap.get("id"):
    return jsonify({"error": "Could not load nation statistics."}), 500
  return jsonify(snap)


@bp.route("/api/bot/nation", methods=["GET"])
def bot_nation():
  err = _require_bot_secret()
  if err:
    return err
  identifier = request.args.get("identifier", "").strip()
  user_id = _resolve_nation_identifier(identifier)
  if user_id is None:
    return jsonify({"error": "Nation not found"}), 404
  snap = nation_snapshot_for_bot(user_id, full_detail=True)
  if not snap.get("id"):
    return jsonify({"error": "Could not load nation statistics."}), 500
  return jsonify(snap)


@bp.route("/api/bot/wars", methods=["GET"])
def bot_wars():
  err = _require_bot_secret()
  if err:
    return err
  identifier = request.args.get("nation", "").strip()
  if identifier:
    user_id = _resolve_nation_identifier(identifier)
  else:
    discord_user_id = _discord_user_id_from_request()
    if not discord_user_id:
      return jsonify({"error": "Register first or provide nation identifier"}), 400
    user_id = resolve_user_id_by_discord(discord_user_id)
  if user_id is None:
    return jsonify({"error": "Nation not found or not registered"}), 404
  return jsonify(
      {
        "nation_id": user_id,
        "wars": _list_active_wars(user_id),
      }
  )


@bp.route("/api/bot/resources", methods=["GET"])
def bot_resources():
  err = _require_bot_secret()
  if err:
    return err
  identifier = request.args.get("nation", "").strip()
  if identifier:
    user_id = _resolve_nation_identifier(identifier)
  else:
    discord_user_id = _discord_user_id_from_request()
    if not discord_user_id:
      return jsonify({"error": "Register first or provide nation identifier"}), 400
    user_id = resolve_user_id_by_discord(discord_user_id)
  if user_id is None:
    return jsonify({"error": "Nation not found or not registered"}), 404
  snap = _nation_snapshot(user_id, include_resources=True)
  return jsonify(snap)


def register_bot_api_routes(app_instance):
  app_instance.register_blueprint(bp)
