"""Authenticated HTTP API for the AnO Discord bot (internal use only)."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from flask import Blueprint, jsonify, request

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

CODE_TTL_MINUTES = 10
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


def _coalition_summary(user_id: int) -> Dict[str, Any]:
  members_tbl = get_coalition_members_table()
  if not members_tbl:
    return {"coalition_id": None, "coalition_name": None, "role": None}
  row = QueryHelper.fetch_one(
      f"""
      SELECT cm.colid, cm.role, c.name
      FROM {members_tbl} cm
      LEFT JOIN colNames c ON c.id = cm.colid
      WHERE cm.userid = %s
      """,
      (user_id,),
      dict_cursor=True,
  )
  if not row:
    return {"coalition_id": None, "coalition_name": None, "role": None}
  return {
    "coalition_id": row.get("colid"),
    "coalition_name": row.get("name"),
    "role": row.get("role"),
  }


def _active_war_count(user_id: int) -> int:
  row = QueryHelper.fetch_one(
      """
      SELECT COUNT(*) FROM wars
      WHERE peace_date IS NULL
        AND (attacker_id = %s OR defender_id = %s)
      """,
      (user_id, user_id),
  )
  return int(row[0]) if row else 0


def _list_active_wars(user_id: int) -> List[Dict[str, Any]]:
  rows = QueryHelper.fetch_all(
      """
      SELECT w.war_id, w.attacker_id, w.defender_id, w.war_type,
             ua.username AS attacker_name, ud.username AS defender_name
      FROM wars w
      JOIN users ua ON ua.id = w.attacker_id
      JOIN users ud ON ud.id = w.defender_id
      WHERE w.peace_date IS NULL
        AND (w.attacker_id = %s OR w.defender_id = %s)
      ORDER BY w.war_id DESC
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


def _nation_snapshot(user_id: int, include_resources: bool = False) -> Dict[str, Any]:
  row = QueryHelper.fetch_one(
      """
      SELECT u.id, u.username, s.location, s.gold
      FROM users u
      INNER JOIN stats s ON s.id = u.id
      WHERE u.id = %s
      """,
      (user_id,),
      dict_cursor=True,
  )
  if not row:
    return {}
  coalition = _coalition_summary(user_id)
  data = get_user_full_data(user_id)
  provinces = data.get("provinces") or {}
  province_count = int(provinces.get("province_count") or 0)

  snapshot: Dict[str, Any] = {
    "id": row["id"],
    "username": row["username"],
    "location": row.get("location"),
    "gold": int(row.get("gold") or 0),
    "influence": get_influence(user_id),
    "coalition": coalition,
    "active_wars": _active_war_count(user_id),
    "province_count": province_count,
  }
  if include_resources:
    resources = UserQueries.get_user_resources(user_id)
    top = sorted(resources.items(), key=lambda x: x[1], reverse=True)[:12]
    snapshot["resources"] = {k: v for k, v in top if v > 0}
  return snapshot


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
  return jsonify({"ok": True, "message": message, "user_id": user_id})


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
  snap = _nation_snapshot(user_id)
  snap["active_wars_list"] = _list_active_wars(user_id)
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
  return jsonify(_nation_snapshot(user_id))


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
