import os
import ast
import json
import glob
import hmac
from time import time
from helpers import error, get_valid_int
from database import get_request_cursor, invalidate_user_cache
from variables import RESOURCES as resources
from .repositories import AdminRepository

def _load_super_admin_ids():
    raw = (os.getenv("SUPER_ADMIN_USER_IDS") or "").strip()
    if raw:
        return {int(x.strip()) for x in raw.split(",") if x.strip().isdigit()}
    return {1, 16, 1215, 69696969}

SUPER_ADMIN_USER_IDS = _load_super_admin_ids()

def admin_only_guard(session_user_id):
    if session_user_id not in SUPER_ADMIN_USER_IDS:
        # Check dynamically for Terra Homeworld
        try:
            with get_request_cursor() as db:
                db.execute("SELECT username FROM users WHERE id = %s", (session_user_id,))
                user = db.fetchone()
                if user and user[0] == 'Terra Homeworld':
                    return None
        except Exception:
            pass
            
        allowed = ", ".join(str(uid) for uid in sorted(SUPER_ADMIN_USER_IDS))
        return error(
            403,
            f"This command center is restricted to nation IDs: {allowed}.",
        )
    return None

_ACTION_LABELS = {
    "admin_add_resource": ("Add Resource", "success"),
    "admin_add_provinces": ("Add Provinces", "success"),
    "admin_ban_user": ("Ban", "danger"),
    "admin_unban_user": ("Unban", "info"),
    "admin_kick_user": ("Kick", "warning"),
    "province_deleted": ("Province Deleted", "muted"),
    "province_created": ("Province Created", "info"),
    "nation_reset": ("Nation Reset", "danger"),
}

def format_action(action):
    label, _ = _ACTION_LABELS.get(action, (action.replace("_", " ").title(), "muted"))
    return label

def action_badge_class(action):
    _, cls = _ACTION_LABELS.get(action, (action, "muted"))
    return cls



def flatten_dict(obj, prefix=""):
    parts = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            label = (
                f"{prefix}{k}".replace("_", " ").title()
                if prefix
                else str(k).replace("_", " ").title()
            )
            if isinstance(v, dict):
                parts.extend(flatten_dict(v, f"{k}."))
            elif isinstance(v, (list, tuple)):
                parts.append((label, ", ".join(str(i) for i in v)))
            else:
                parts.append((label, str(v)))
    else:
        parts.append((prefix.rstrip(".").title() or "Value", str(obj)))
    return parts

def parse_details(raw):
    if not raw:
        return []
    if isinstance(raw, (dict, list)):
        return flatten_dict(raw)
    if raw.startswith("{") or raw.startswith("("):
        try:
            obj = ast.literal_eval(raw)
            return flatten_dict(obj)
        except Exception:
            return [("Details", raw)]
    parts = []
    for token in raw.split():
        if "=" in token:
            key, _, val = token.partition("=")
            parts.append((key.replace("_", " ").title(), val))
        else:
            parts.append(("Info", token))
    return parts



def get_admin_command_center_data():
    with get_request_cursor() as db:
        AdminRepository.ensure_admin_tables(db)
        controlled_users = AdminRepository.get_controlled_users(db)
        recent_actions = AdminRepository.get_recent_actions(db)
        new_accounts_by_day = AdminRepository.get_new_accounts_by_day(db)
        
    new_accounts_total = sum(row[1] for row in new_accounts_by_day)

    parsed_actions = []
    for row in recent_actions:
        actor_id, actor_name, action, target_id, target_name, raw_details, ts = row
        details_parts = parse_details(raw_details or "")
        parsed_actions.append({
            "actor_id": actor_id,
            "actor_name": actor_name,
            "action": format_action(action),
            "action_raw": action,
            "target_id": target_id,
            "target_name": target_name,
            "details": details_parts,
            "time": ts,
        })

    return {
        "controlled_users": controlled_users,
        "recent_actions": parsed_actions,
        "new_accounts_by_day": new_accounts_by_day,
        "new_accounts_total": new_accounts_total,
        "RESOURCES": resources,
    }

def process_add_resource(actor, target_user_id, amount, resource):
    try:
        with get_request_cursor() as db:
            AdminRepository.ensure_admin_tables(db)
            target_row = AdminRepository.validate_target_user(db, target_user_id)
            if not target_row:
                return error(404, "Target user not found")
    
            if resource in ["money", "gold"]:
                AdminRepository.add_gold(db, target_user_id, amount)
                money_row = AdminRepository.get_resource_id_by_name(db, "money")
                if money_row:
                    AdminRepository.add_resource_quantity(db, target_user_id, money_row[0], amount)
                AdminRepository.log_admin_action(db, actor, "admin_add_resource", target_user_id, f"resource=money amount={amount}")
            else:
                resource_row = AdminRepository.get_active_resource_id_by_name(db, resource)
                if not resource_row:
                    return error(400, "Unknown or inactive resource")
                AdminRepository.add_resource_quantity(db, target_user_id, resource_row[0], amount)
                AdminRepository.log_admin_action(db, actor, "admin_add_resource", target_user_id, f"resource={resource} amount={amount}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        return error(500, "Database transaction failed. Please try again.")

    try:
        invalidate_user_cache(target_user_id)
    except Exception:
        pass
    return None

def process_add_provinces(actor, target_user_id, amount):
    if amount <= 0 or amount > 50:
        return error(400, "Province amount must be between 1 and 50")

    with get_request_cursor() as db:
        AdminRepository.ensure_admin_tables(db)
        target_row = AdminRepository.validate_target_user(db, target_user_id)
        if not target_row:
            return error(404, "Target user not found")

        current_max = AdminRepository.get_max_province_id(db, target_user_id)
        for idx in range(1, amount + 1):
            AdminRepository.add_province(db, target_user_id, f"Admin Province {current_max + idx}")

        AdminRepository.log_admin_action(db, actor, "admin_add_provinces", target_user_id, f"amount={amount}")

    try:
        invalidate_user_cache(target_user_id)
    except Exception:
        pass
    return None

def process_ban_user(actor, target_user_id, reason):
    if target_user_id in SUPER_ADMIN_USER_IDS:
        return error(400, "Cannot ban a privileged admin nation")

    with get_request_cursor() as db:
        AdminRepository.ensure_admin_tables(db)
        target_row = AdminRepository.validate_target_user(db, target_user_id)
        if not target_row:
            return error(404, "Target user not found")

        AdminRepository.set_user_ban_status(db, target_user_id, True, reason, True)
        AdminRepository.log_admin_action(db, actor, "admin_ban_user", target_user_id, f"reason={reason}")
    return None

def process_unban_user(actor, target_user_id):
    with get_request_cursor() as db:
        AdminRepository.ensure_admin_tables(db)
        target_row = AdminRepository.validate_target_user(db, target_user_id)
        if not target_row:
            return error(404, "Target user not found")

        AdminRepository.set_user_ban_status(db, target_user_id, False, None, False)
        AdminRepository.log_admin_action(db, actor, "admin_unban_user", target_user_id, "")
    return None

def process_kick_user(actor, target_user_id, reason):
    if target_user_id in SUPER_ADMIN_USER_IDS:
        return error(400, "Cannot kick a privileged admin nation")

    with get_request_cursor() as db:
        AdminRepository.ensure_admin_tables(db)
        target_row = AdminRepository.validate_target_user(db, target_user_id)
        if not target_row:
            return error(404, "Target user not found")

        AdminRepository.set_user_ban_status(db, target_user_id, False, None, True)
        AdminRepository.log_admin_action(db, actor, "admin_kick_user", target_user_id, f"reason={reason}")
    return None


def take_economy_snapshot():
    with get_request_cursor() as db:
        AdminRepository.take_economy_snapshot(db)

def get_economy_dashboard_data():
    with get_request_cursor() as db:
        AdminRepository.ensure_admin_tables(db)
        current_totals = AdminRepository.get_current_totals(db)
        snapshot_count = AdminRepository.get_snapshot_count(db)
    
    resource_list = ["gold"] + resources
    return {
        "current_totals": current_totals,
        "snapshot_count": snapshot_count,
        "resource_list": resource_list,
    }

def get_economy_api_data(resource, days):
    valid_resources = {"gold"} | set(resources)
    if resource not in valid_resources:
        return {"error": "Unknown resource"}, 400

    with get_request_cursor() as db:
        AdminRepository.ensure_admin_tables(db)
        rows = AdminRepository.get_snapshot_time_series(db, resource, days)

    data = {
        "resource": resource,
        "labels": [r[0].strftime("%m/%d %H:%M") for r in rows],
        "totals": [int(r[1]) for r in rows],
        "player_counts": [int(r[2]) for r in rows],
    }
    return data, 200

def trigger_tasks_service(secret, header):
    if not secret:
        return "Admin diagnostics not configured", 503
    if not hmac.compare_digest(header, secret):
        return "Forbidden", 403

    results = {}
    try:
        import redis as redis_lib
        import urllib.parse as _urlparse

        redis_url = os.getenv("REDIS_URL") or os.getenv("REDIS_PUBLIC_URL")
        if redis_url:
            parsed = _urlparse.urlparse(redis_url)
            r = redis_lib.Redis(
                host=parsed.hostname,
                port=parsed.port or 6379,
                password=parsed.password,
            )
            deleted_beat = r.delete("beat:leader")
            results["beat_leader_lock_cleared"] = bool(deleted_beat)

            task_locks = list(r.keys("task_lock:*"))
            for key in task_locks:
                r.delete(key)
            results["task_locks_cleared"] = len(task_locks)
        else:
            results["redis"] = "no REDIS_URL found"
    except Exception as e:
        results["redis_error"] = str(e)

    try:
        from tasks import celery as celery_app
        celery_app.send_task("tasks.task_global_tick")
        celery_app.send_task("tasks.task_generate_province_revenue")
        celery_app.send_task("tasks.task_tax_income")
        results["tasks_sent"] = [
            "global_tick",
            "generate_province_revenue",
            "tax_income",
        ]
    except Exception as e:
        results["task_send_error"] = str(e)

    return results, 200

def admin_ai_agent_service(diag_secret, agent_password, diag_header, password_header, user_id=None):
    from helpers import validate_post_origin
    blocked = validate_post_origin()
    if blocked is not None:
        return blocked, 403

    if not diag_secret or not agent_password:
        return {"error": "Admin AI agent not configured"}, 503

    if not hmac.compare_digest(diag_header, diag_secret):
        return "Forbidden", 403
    if not hmac.compare_digest(password_header, agent_password):
        return "Forbidden", 403

    try:
        from ai_agent import run_ai_agent
        result = run_ai_agent(user_id)
        return result, 200
    except Exception as e:
        return {"error": str(e)}, 500

def get_ai_logs(secret, header):
    if not secret:
        return "Admin diagnostics not configured", 503
    if not hmac.compare_digest(header, secret):
        return "Forbidden", 403

    log_dir = os.path.join(os.path.dirname(__file__), "..", "..", "ai_logs")
    if not os.path.exists(log_dir):
        # Fallback to the same dir as admin_bp.py used
        log_dir = os.path.join(os.path.dirname(__file__), "..", "ai_logs")
        if not os.path.exists(log_dir):
            log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "ai_logs")
            if not os.path.exists(log_dir):
                return {"logs": [], "summary": "No logs yet"}, 200

    files = sorted(glob.glob(os.path.join(log_dir, "cycle_*.json")), reverse=True)[:10]
    logs = []
    for fp in files:
        try:
            with open(fp) as f:
                logs.append(json.loads(f.read()))
        except Exception:
            pass

    summary_path = os.path.join(log_dir, "summary.csv")
    summary = ""
    if os.path.exists(summary_path):
        with open(summary_path) as f:
            summary = f.read()

    return {"logs": logs, "summary": summary}, 200

