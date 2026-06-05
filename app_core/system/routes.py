from flask import Blueprint, current_app
import os

bp = Blueprint('system_bp', __name__)

@bp.route("/health")
def health(): return "ok", 200

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

    try:
        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute('''SELECT task_name, last_run, EXTRACT(EPOCH FROM (now() - last_run))::int AS age_seconds
                          FROM task_runs WHERE task_name IN ('generate_province_revenue', 'global_tick', 'tax_income', 'population_growth')
                          ORDER BY task_name''')
            economy = {}
            max_rev = int(os.getenv("READY_MAX_REVENUE_AGE_SECONDS", "7200"))
            for name, last_run, age in db.fetchall():
                entry = {
                    "last_run": last_run.isoformat() if last_run else None,
                    "age_seconds": int(age) if age is not None else None,
                }
                if name == "generate_province_revenue" and age is not None: entry["stale"] = int(age) > max_rev
                economy[name] = entry
            payload["economy_tasks"] = economy
    except Exception as exc: payload["economy_tasks_error"] = str(exc)[:200]
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
