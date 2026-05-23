"""Authenticated HTTP API for the AnO Discord bot (internal use only)."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
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


def _bot_secret() -> Optional[str]:
    explicit = (os.getenv("BOT_API_SECRET") or "").strip()
    if explicit:
        return explicit
    # Bootstrap when BOT_API_SECRET is not set yet (same derivation on web + discord-bot).
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


def _resolve_nation_identifier(identifier: str) -> Optional[int]:
  if not identifier or not str(identifier).strip():
    return None
  raw = str(identifier).strip()
  if raw.isdigit():
    row = QueryHelper.fetch_one(
      "SELECT id FROM users WHERE id = %s", (int(raw),)
    )
    return int(row[0]) if row else None
  row = QueryHelper.fetch_one(
      "SELECT id FROM users WHERE LOWER(username) = LOWER(%s) LIMIT 1",
      (raw,),
  )
  return int(row[0]) if row else None


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


def _coalition_summary(user_id: int) -> Dict[str, Any]:
    members_tbl = get_coalition_members_table()
    if not members_tbl:
        return {
            "coalition_id": None,
            "coalition_name": None,
            "role": None,
            "tax_rate": 0,
        }
    row = QueryHelper.fetch_one(
        f"""
        SELECT cm.colid, cm.role, c.name, COALESCE(c.tax_rate, 0) AS tax_rate
        FROM {members_tbl} cm
        LEFT JOIN colNames c ON c.id = cm.colid
        WHERE cm.userid = %s
        """,
        (user_id,),
        dict_cursor=True,
    )
    if not row:
        return {
            "coalition_id": None,
            "coalition_name": None,
            "role": None,
            "tax_rate": 0,
        }
    return {
        "coalition_id": row.get("colid"),
        "coalition_name": row.get("name"),
        "role": row.get("role"),
        "tax_rate": int(row.get("tax_rate") or 0),
    }


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


def _list_active_wars(user_id: int) -> List[Dict[str, Any]]:
    schema = _wars_schema()
    war_pk, atk, dfn = schema.get("war_pk"), schema.get("attacker"), schema.get("defender")
    if not war_pk or not atk or not dfn:
        return []
    rows = QueryHelper.fetch_all(
        f"""
        SELECT w.{war_pk} AS war_id, w.{atk} AS attacker_id, w.{dfn} AS defender_id,
               w.war_type,
               ua.username AS attacker_name, ud.username AS defender_name
        FROM wars w
        JOIN users ua ON ua.id = w.{atk}
        JOIN users ud ON ud.id = w.{dfn}
        WHERE w.peace_date IS NULL
          AND (w.{atk} = %s OR w.{dfn} = %s)
        ORDER BY w.{war_pk} DESC
        """,
        (user_id, user_id),
        dict_cursor=True,
    )
    wars: List[Dict[str, Any]] = []
    for row in rows or []:
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
        snap = _nation_snapshot(
            user_id, include_resources=include_resources or full_detail
        )
        if not snap:
            return {}
        if full_detail:
            _enrich_nation_snapshot(snap, user_id)
        try:
            snap["active_wars_list"] = _list_active_wars(user_id)
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
