import hmac
import os
from flask import Blueprint, request, render_template, session, redirect, jsonify, current_app, flash
from helpers import login_required, get_valid_int
from .services import (
    admin_only_guard, get_admin_command_center_data, process_add_resource, process_add_provinces,
    process_ban_user, process_unban_user, process_kick_user, get_economy_dashboard_data,
    get_economy_api_data, take_economy_snapshot, trigger_tasks_service, admin_ai_agent_service,
    get_ai_logs, action_badge_class
)
from .guards import admin_diag_authorized, admin_diag_denied_response, admin_diag_or_session
from .repositories import AdminRepository

admin_bp = Blueprint('admin', __name__)


def _require_admin_diag_or_session():
    if not admin_diag_or_session(session.get("user_id")):
        return admin_diag_denied_response()
    return None

@admin_bp.record
def record_params(setup_state):
    app = setup_state.app
    app.jinja_env.globals["action_badge_class"] = action_badge_class

@admin_bp.route("/_admin/trigger_tasks")
def trigger_tasks():
    secret = os.getenv("ADMIN_DIAG_SECRET")
    header = request.headers.get("X-DIAG-SECRET") or ""
    results, status = trigger_tasks_service(secret, header)
    if isinstance(results, str):
        return results, status
    return jsonify(results), status

@admin_bp.route("/_admin/ai_agent", methods=["POST"])
def admin_ai_agent():
    diag_secret = os.getenv("ADMIN_DIAG_SECRET")
    agent_password = os.getenv("AI_AGENT_PASSWORD")
    diag_header = request.headers.get("X-DIAG-SECRET") or ""
    password_header = request.headers.get("X-AI-AGENT-PASSWORD") or ""
    
    user_id = None
    if request.is_json:
        user_id = request.json.get("user_id")

    res, status = admin_ai_agent_service(diag_secret, agent_password, diag_header, password_header, user_id)
    if isinstance(res, str):
        return res, status
    return jsonify(res), status

@admin_bp.route("/_admin/ai_logs")
def admin_ai_logs_route():
    secret = os.getenv("ADMIN_DIAG_SECRET")
    header = request.headers.get("X-DIAG-SECRET") or ""
    res, status = get_ai_logs(secret, header)
    if isinstance(res, str):
        return res, status
    return jsonify(res), status

@admin_bp.route("/_admin/db_diagnostics")
def db_diagnostics():
    secret = os.getenv("ADMIN_DIAG_SECRET")
    header = request.headers.get("X-DIAG-SECRET") or ""
    if not secret or not __import__('hmac').compare_digest(header, secret):
        return "Forbidden", 403

    try:
        action = request.args.get("action")
        out = AdminRepository.get_db_diagnostics(action)
        if "error" in out:
            return jsonify(out), 500
        return jsonify(out), 200
    except Exception as e:
        current_app.logger.exception("DB diagnostics failed")
        return jsonify({"error": str(e)}), 500

@admin_bp.route("/admin/init-database-DO-NOT-RUN-TWICE", methods=["GET"])
def admin_init_database():
    return "Database already initialized. Remove this route from app.py", 200

@admin_bp.route("/admin/debug_wealth")
@login_required
def admin_debug_wealth():
    denied = _require_admin_diag_or_session()
    if denied:
        return denied
    resources = AdminRepository.get_debug_wealth()
    html = "<h3>Resource Dictionary</h3><table border='1'><tr><th>ID</th><th>Name</th><th>Display</th></tr>"
    for res in resources:
        html += f"<tr><td>{res[0]}</td><td>{res[1]}</td><td>{res[2]}</td></tr>"
    html += "</table>"
    return html

@admin_bp.route("/admin/migrate_treaties")
@login_required
def admin_migrate_treaties():
    denied = _require_admin_diag_or_session()
    if denied:
        return denied
    success, msg = AdminRepository.migrate_treaties()
    return msg, 200 if success else 500

@admin_bp.route("/admin/live-feed")
@login_required
def admin_live_feed():
    denied = _require_admin_diag_or_session()
    if denied:
        return denied
    try:
        data = AdminRepository.get_live_feed()
        formatted_wars = []
        for w in data['wars']:
            status = "Active" if w[4] is None else "Peacetime"
            formatted_wars.append((w[0], w[1], w[2], w[3], status))
        return render_template("admin_live_feed.html", users=data['users'], attempts=data['attempts'], news=data['news'], wars=formatted_wars, wealth=data['wealth'], offers=data['offers'], trades=data['trades'])
    except Exception as e:
        return f"Database Error: {e}", 500

@admin_bp.route("/admin/debug/leviathan")
@login_required
def debug_leviathan():
    denied = _require_admin_diag_or_session()
    if denied:
        return denied
    wipe_secret = (os.getenv("ADMIN_WIPE_SECRET") or "").strip()
    pass_code = (request.args.get("pass") or "").strip()
    wipe_now = bool(wipe_secret and pass_code and hmac.compare_digest(pass_code, wipe_secret))
    wipe_provinces = bool(
        wipe_secret
        and pass_code
        and hmac.compare_digest(pass_code, f"{wipe_secret}:provinces")
    )
    if pass_code and not wipe_now and not wipe_provinces:
        return "Unauthorized", 401
    try:
        data, err = AdminRepository.get_leviathan_debug(
            wipe_now=wipe_now, wipe_provinces=wipe_provinces
        )
        if err:
            return jsonify({"error": err})
        return jsonify(data)
    except Exception as e:
        return f"Database Error: {e}", 500

@admin_bp.route("/admin/debug/exploits")
@login_required
def debug_exploits():
    denied = _require_admin_diag_or_session()
    if denied:
        return denied
    try:
        wipe = request.args.get("wipe") == "true"
        data = AdminRepository.get_exploits_debug(wipe)
        if wipe:
            return jsonify({"status": "Wiped all suspicious users and banks across the entire server!"})
        return jsonify(data)
    except Exception as e:
        return f"Database Error: {e}", 500

# ----- command center routes -----

@admin_bp.route("/admin/command-center", methods=["GET"])
@login_required
def admin_command_center():
    denied = admin_only_guard(session.get("user_id"))
    if denied: return denied
    data = get_admin_command_center_data()
    return render_template("admin_command_center.html", **data)

@admin_bp.route("/admin/command-center/add-resource", methods=["POST"])
@login_required
def admin_add_resource():
    denied = admin_only_guard(session.get("user_id"))
    if denied: return denied
    target_user_id, err = get_valid_int("target_user_id", error_invalid="Invalid user ID or amount", error_min="Target user ID must be positive")
    if err: return err
    amount, err = get_valid_int("amount", error_invalid="Invalid user ID or amount", error_min="Amount must be positive")
    if err: return err
    resource = (request.form.get("resource") or "").strip().lower()
    if not resource: return error(400, "Resource is required")
    
    err = process_add_resource(session["user_id"], target_user_id, amount, resource)
    if err: return err
    
    flash(f"Added {amount} {resource} to user {target_user_id}")
    return redirect("/admin/command-center")

@admin_bp.route("/admin/command-center/add-provinces", methods=["POST"])
@login_required
def admin_add_provinces():
    denied = admin_only_guard(session.get("user_id"))
    if denied: return denied
    target_user_id, err = get_valid_int("target_user_id", error_invalid="Invalid user ID or amount", error_min="Target user ID must be positive")
    if err: return err
    amount, err = get_valid_int("amount", error_invalid="Invalid user ID or amount")
    if err: return err
    
    err_res = process_add_provinces(session["user_id"], target_user_id, amount)
    if err_res: return err_res
    
    flash(f"Added {amount} province(s) to user {target_user_id}")
    return redirect("/admin/command-center")

@admin_bp.route("/admin/command-center/ban-user", methods=["POST"])
@login_required
def admin_ban_user():
    denied = admin_only_guard(session.get("user_id"))
    if denied: return denied
    target_user_id, err = get_valid_int("target_user_id", error_invalid="Invalid user ID", error_min="Target user ID must be positive")
    if err: return err
    reason = (request.form.get("reason") or "No reason provided").strip()
    
    err_res = process_ban_user(session["user_id"], target_user_id, reason)
    if err_res: return err_res
    
    flash(f"Banned user {target_user_id}")
    return redirect("/admin/command-center")

@admin_bp.route("/admin/command-center/unban-user", methods=["POST"])
@login_required
def admin_unban_user():
    denied = admin_only_guard(session.get("user_id"))
    if denied: return denied
    target_user_id, err = get_valid_int("target_user_id", error_invalid="Invalid user ID", error_min="Target user ID must be positive")
    if err: return err
    
    err_res = process_unban_user(session["user_id"], target_user_id)
    if err_res: return err_res
    
    flash(f"Unbanned user {target_user_id}")
    return redirect("/admin/command-center")

@admin_bp.route("/admin/command-center/kick-user", methods=["POST"])
@login_required
def admin_kick_user():
    denied = admin_only_guard(session.get("user_id"))
    if denied: return denied
    target_user_id, err = get_valid_int("target_user_id", error_invalid="Invalid user ID", error_min="Target user ID must be positive")
    if err: return err
    reason = (request.form.get("reason") or "No reason provided").strip()
    
    err_res = process_kick_user(session["user_id"], target_user_id, reason)
    if err_res: return err_res
    
    flash(f"Kick queued for user {target_user_id}")
    return redirect("/admin/command-center")

@admin_bp.route("/admin/command-center/economy", methods=["GET"])
@login_required
def admin_economy_dashboard():
    denied = admin_only_guard(session.get("user_id"))
    if denied: return denied
    data = get_economy_dashboard_data()
    return render_template("admin_economy.html", **data)

@admin_bp.route("/admin/command-center/economy/api", methods=["GET"])
@login_required
def admin_economy_api():
    denied = admin_only_guard(session.get("user_id"))
    if denied: return denied
    resource = request.args.get("resource", "gold").strip().lower()
    days = min(int(request.args.get("days", "7")), 90)
    data, status = get_economy_api_data(resource, days)
    return jsonify(data), status

@admin_bp.route("/admin/command-center/economy/snapshot", methods=["POST"])
@login_required
def admin_trigger_snapshot():
    denied = admin_only_guard(session.get("user_id"))
    if denied: return denied
    take_economy_snapshot()
    flash("Economy snapshot taken successfully.")
    return redirect("/admin/command-center/economy")
