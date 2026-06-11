from flask import Blueprint, current_app, jsonify
import os

bp = Blueprint('system_bp', __name__)

_ECONOMY_TASKS = (
    "generate_province_revenue",
    "global_tick",
    "tax_income",
    "population_growth",
)


def _economy_task_payload() -> dict:
    from database import get_db_connection

    payload = {"ok": True, "tasks": {}, "stale": False}
    try:
        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute(
                """
                SELECT task_name, last_run,
                       EXTRACT(EPOCH FROM (now() - last_run))::int AS age_seconds
                FROM task_runs
                WHERE task_name = ANY(%s)
                """,
                (list(_ECONOMY_TASKS),),
            )
            rows = {name: (last_run, age) for name, last_run, age in db.fetchall()}
        thresholds = {
            "generate_province_revenue": int(os.getenv("READY_MAX_REVENUE_AGE_SECONDS", "7200")),
            "global_tick": int(os.getenv("GLOBAL_TICK_STALE_SECONDS", "1800")),
            "tax_income": int(os.getenv("TAX_INCOME_STALE_SECONDS", "7200")),
            "population_growth": int(os.getenv("POP_GROWTH_STALE_SECONDS", "7200")),
        }
        for name in _ECONOMY_TASKS:
            last_run, age = rows.get(name, (None, None))
            entry = {
                "last_run": last_run.isoformat() if last_run else None,
                "age_seconds": int(age) if age is not None else None,
                "age_minutes": round(int(age) / 60) if age is not None else None,
            }
            limit = thresholds.get(name, 7200)
            if age is None or int(age) > limit:
                entry["stale"] = True
                payload["stale"] = True
            else:
                entry["stale"] = False
            payload["tasks"][name] = entry
    except Exception as exc:
        payload["ok"] = False
        payload["error"] = str(exc)[:200]
    return payload

@bp.route("/health")
def health(): return "ok", 200

@bp.route("/api/economy/status", methods=["GET"])
def economy_status():
    """Player-safe economy heartbeat (task freshness)."""
    return jsonify(_economy_task_payload())


@bp.route("/deploy-info")
def deploy_info():
    from database import schema_compat_failed_steps, schema_compat_succeeded, get_db_connection
    payload = {
        "git_commit": os.getenv("RAILWAY_GIT_COMMIT_SHA") or os.getenv("GIT_COMMIT") or "unknown",
        "schema_compat": "ok" if schema_compat_succeeded() else "failed",
        "boot_marker": os.getenv("ANO_BOOT_MARKER", "unknown"),
        "start_command": "start_production.sh" if os.getenv("ANO_USE_START_SCRIPT", "1") == "1" else "procfile/gunicorn",
    }
    failures = schema_compat_failed_steps()
    if failures: payload["schema_compat_errors"] = failures[:8]

    eco = _economy_task_payload()
    payload["economy_tasks"] = eco.get("tasks", {})
    payload["economy_stale"] = eco.get("stale", False)
    if not eco.get("ok"):
        payload["economy_tasks_error"] = eco.get("error", "unknown")
    return payload, 200

@bp.route("/ready")
def ready():
    from database import get_db_connection, schema_compat_succeeded
    checks = {}
    try:
        if not schema_compat_succeeded():
            checks["schema_compat"] = "failed"
            return {"status": "not ready", "checks": checks}, 503

        max_revenue_age = int(os.getenv("READY_MAX_REVENUE_AGE_SECONDS", "7200"))
        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute("SELECT 1")
            db.fetchone()
            db.execute("SELECT to_regclass('public.resource_dictionary')")
            if db.fetchone()[0] is None:
                checks["resource_dictionary"] = "missing"
                return {"status": "not ready", "checks": checks}, 503
            db.execute("SELECT EXTRACT(EPOCH FROM (now() - last_run)) FROM task_runs WHERE task_name = 'generate_province_revenue'")
            row = db.fetchone()
            if not row or row[0] is None: checks["generate_province_revenue"] = "no last_run"
            elif float(row[0]) > max_revenue_age: checks["generate_province_revenue"] = f"stale>{max_revenue_age}s"
            else: checks["generate_province_revenue"] = "ok"
        if checks.get("generate_province_revenue", "ok") != "ok":
            current_app.logger.warning("Readiness: %s", checks)
            return {"status": "not ready", "checks": checks}, 503
        return {"status": "ok", "checks": checks}, 200
    except Exception as e:
        current_app.logger.warning("Readiness check failed: %s", e)
        return {"status": "not ready", "error": str(e)}, 503
