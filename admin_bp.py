from flask import Blueprint, request, render_template, session, redirect, jsonify, current_app, send_from_directory, flash
import os
import hmac
import json
import time

admin_bp = Blueprint('admin', __name__)

@admin_bp.route("/_admin/trigger_tasks")
def trigger_tasks():
    """Admin endpoint to clear stale Redis locks and trigger Celery tasks.

    Security: Requires ADMIN_DIAG_SECRET env var and matching X-DIAG-SECRET header.
    This is used when the Celery beat process died during a deploy and tasks
    aren't being scheduled.
    """
    secret = os.getenv("ADMIN_DIAG_SECRET")
    if not secret:
        return "Admin diagnostics not configured", 503
    header = request.headers.get("X-DIAG-SECRET") or ""
    if not hmac.compare_digest(header, secret):
        return "Forbidden", 403

    results = {}

    # 1. Clear stale Redis locks
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
            # Clear beat leader lock
            deleted_beat = r.delete("beat:leader")
            results["beat_leader_lock_cleared"] = bool(deleted_beat)

            # Clear any stale task locks
            task_locks = list(r.keys("task_lock:*"))
            for key in task_locks:
                r.delete(key)
            results["task_locks_cleared"] = len(task_locks)
        else:
            results["redis"] = "no REDIS_URL found"
    except Exception as e:
        results["redis_error"] = str(e)

    # 2. Try to send tasks to the Celery queue
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

    return results


@admin_bp.route("/_admin/ai_agent", methods=["POST"])
def admin_ai_agent():
    """Admin endpoint to manually trigger the AI agent.

    Requires ADMIN_DIAG_SECRET (X-DIAG-SECRET) and AI_AGENT_PASSWORD (X-AI-AGENT-PASSWORD).
    POST body can include JSON {"user_id": 1} to override target user.
    """
    from helpers import validate_post_origin

    blocked = validate_post_origin()
    if blocked is not None:
        return blocked

    diag_secret = os.getenv("ADMIN_DIAG_SECRET")
    agent_password = os.getenv("AI_AGENT_PASSWORD")
    if not diag_secret or not agent_password:
        return {"error": "Admin AI agent not configured"}, 503

    diag_header = request.headers.get("X-DIAG-SECRET") or ""
    password_header = request.headers.get("X-AI-AGENT-PASSWORD") or ""
    if not hmac.compare_digest(diag_header, diag_secret):
        return "Forbidden", 403
    if not hmac.compare_digest(password_header, agent_password):
        return "Forbidden", 403

    try:
        from ai_agent import run_ai_agent

        user_id = None
        if request.is_json:
            user_id = request.json.get("user_id")

        result = run_ai_agent(user_id)
        return result
    except Exception as e:
        return {"error": str(e)}, 500


@admin_bp.route("/_admin/ai_logs")
def admin_ai_logs():
    """View recent AI agent decision logs."""
    import glob as _glob

    secret = os.getenv("ADMIN_DIAG_SECRET")
    if not secret:
        return "Admin diagnostics not configured", 503
    header = request.headers.get("X-DIAG-SECRET") or ""
    if not hmac.compare_digest(header, secret):
        return "Forbidden", 403

    log_dir = os.path.join(os.path.dirname(__file__), "ai_logs")
    if not os.path.exists(log_dir):
        return {"logs": [], "summary": "No logs yet"}

    # Return last 10 log files
    files = sorted(_glob.glob(os.path.join(log_dir, "cycle_*.json")), reverse=True)[:10]
    logs = []
    for fp in files:
        try:
            with open(fp) as f:
                logs.append(json.loads(f.read()))
        except Exception:
            pass

    # Return summary CSV if it exists
    summary_path = os.path.join(log_dir, "summary.csv")
    summary = ""
    if os.path.exists(summary_path):
        with open(summary_path) as f:
            summary = f.read()

    return {"logs": logs, "summary": summary}


@admin_bp.route("/_admin/db_diagnostics")
def db_diagnostics():
    """Temporary admin-only endpoint to gather short DB diagnostics.

    Security: Requires `ADMIN_DIAG_SECRET` env var and matching `X-DIAG-SECRET` header.
    Output: JSON with max_connections, active connection counts, top non-idle queries,
    and top pg_stat_statements if available. This endpoint is intended for short
    introspection and will be removed when diagnostics are complete.
    """
    secret = os.getenv("ADMIN_DIAG_SECRET")
    header = request.headers.get("X-DIAG-SECRET") or ""
    if not secret or not hmac.compare_digest(header, secret):
        return "Forbidden", 403

    try:
        from database import get_db_connection
        from psycopg2.extras import RealDictCursor

        action = request.args.get("action")

        with get_db_connection() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)

            # Admin action: enable pg_stat_statements extension if allowed
            if action == "enable_pg_stat_statements":
                try:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements;")
                    conn.commit()
                    return {"enabled": True}, 200
                except Exception as e:
                    # Return the error for visibility (coerce to str)
                    return {"enabled": False, "error": str(e)}, 500

            # Admin action: run pre-approved EXPLAIN ANALYZE checks
            if action and action.startswith("explain_"):
                kind = action.split("explain_", 1)[1]
                try:
                    if kind == "infra":
                        sql = (
                            "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) "
                            "SELECT ub.user_id, bd.name, ub.quantity "
                            "FROM user_buildings ub "
                            "INNER JOIN building_dictionary bd "
                            "ON ub.building_id = bd.building_id "
                            "ORDER BY ub.user_id ASC LIMIT 500;"
                        )
                    elif kind == "stats":
                        sql = (
                            "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) "
                            "SELECT id, gold FROM stats "
                            "ORDER BY id ASC LIMIT 500;"
                        )
                    elif kind == "stats_full":
                        sql = (
                            "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) "
                            "SELECT id, gold FROM stats WHERE id IN "
                            "(SELECT id FROM users) LIMIT 10000;"
                        )
                    else:
                        return {"error": "unknown explain target"}, 400

                    cur.execute(sql)
                    rows = cur.fetchall()
                    # rows is JSON plan in first column
                    return {"result": rows}, 200
                except Exception as e:
                    return {"error": str(e)}, 500

            # Normal snapshot (same as before)
            cur.execute("SHOW max_connections;")
            max_conn = cur.fetchone()

            cur.execute("SELECT count(*) FROM pg_stat_activity;")
            active = cur.fetchone()

            cur.execute("SELECT state, count(*) FROM pg_stat_activity GROUP BY state;")
            states = cur.fetchall()

            cur.execute(
                """
                SELECT pid, usename, state, now() - query_start AS duration,
                       left(query, 1000) AS query
                FROM pg_stat_activity
                WHERE state <> 'idle' AND query <> '<IDLE>'
                ORDER BY duration DESC
                LIMIT 20
                """
            )
            long_queries = cur.fetchall()

            # Convert non-JSON-serializable types (e.g., timedelta) to strings
            import datetime as _dt

            serialized_long = []
            for row in long_queries:
                r = dict(row)
                if isinstance(r.get("duration"), _dt.timedelta):
                    r["duration"] = str(r["duration"])
                if "query" in r and isinstance(r["query"], str):
                    # truncate to avoid massive payloads
                    r["query"] = r["query"][:1000]
                serialized_long.append(r)

            out = {
                "max_connections": max_conn,
                "active_connections": active,
                "states": states,
                "long_queries": serialized_long,
            }

            try:
                cur.execute(
                    """
                    SELECT query, calls, total_time, mean_time
                    FROM pg_stat_statements
                    ORDER BY total_time DESC
                    LIMIT 20;
                    """
                )
                out["pg_stat_statements"] = cur.fetchall()
            except Exception:
                out["pg_stat_statements"] = "unavailable"

            # Ensure everything is JSON-serializable by coercing unknown types to str
            def _make_serializable(obj):
                if isinstance(obj, dict):
                    return {k: _make_serializable(v) for k, v in obj.items()}
                if isinstance(obj, list):
                    return [_make_serializable(v) for v in obj]
                if isinstance(obj, (str, int, float, bool)) or obj is None:
                    return obj
                return str(obj)

            out = _make_serializable(out)

        return out, 200
    except Exception as e:
        app.logger.exception("DB diagnostics failed")
        return {"error": str(e)}, 500

@admin_bp.route("/admin/init-database-DO-NOT-RUN-TWICE", methods=["GET"])
def admin_init_database():
    return "Database already initialized. Remove this route from app.py", 200


@admin_bp.route("/admin/debug_wealth")
def admin_debug_wealth():
    """Temporary route to debug the resource dictionary in production."""
    with get_request_cursor(read_only=True) as db:
        db.execute(
            """
            SELECT resource_id, name, display_name 
            FROM resource_dictionary 
            ORDER BY resource_id;
            """
        )
        resources = db.fetchall()
        
        # Format the output for HTML readability
        html = "<h3>Resource Dictionary</h3><table border='1'><tr><th>ID</th><th>Name</th><th>Display</th></tr>"
        for res in resources:
            html += f"<tr><td>{res[0]}</td><td>{res[1]}</td><td>{res[2]}</td></tr>"
        html += "</table>"
        
        return html

@admin_bp.route("/admin/migrate_treaties")
def admin_migrate_treaties():
    from database import get_db_connection
    conn = get_db_connection()
    db = conn.cursor()
    try:
        db.execute("""
            CREATE TABLE IF NOT EXISTS treaties (
                id SERIAL PRIMARY KEY,
                sender_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                recipient_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                treaty_type VARCHAR(50) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(sender_id, recipient_id, treaty_type)
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS poll_votes (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                poll_name VARCHAR(50) NOT NULL,
                vote_option VARCHAR(50) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, poll_name)
            )
        """)
        conn.commit()
        return "Treaties and Poll tables migrated successfully!", 200
    except Exception as e:
        conn.rollback()
        return f"Error: {e}", 500
    finally:
        db.close()
        conn.close()


@admin_bp.route("/admin/live-feed")
def admin_live_feed():
    from flask import request, render_template
    if request.args.get("pass") != "AnOAdminSecure2026!":
        return "Unauthorized", 401
        
    from database import get_request_cursor
    try:
        with get_request_cursor() as db:
            db.execute("SELECT id, username, email, date FROM users ORDER BY id DESC LIMIT 20")
            users = db.fetchall()
            db.execute("SELECT ip_address, attempt_time, successful FROM signup_attempts ORDER BY attempt_time DESC LIMIT 20")
            attempts = db.fetchall()
            db.execute("SELECT id, destination_id, message, date FROM news ORDER BY id DESC LIMIT 20")
            news = db.fetchall()
            db.execute("SELECT id, attacker, defender, war_type, peace_date FROM wars ORDER BY id DESC LIMIT 10")
            wars = db.fetchall()
            db.execute("SELECT u.id, u.username, s.gold FROM users u JOIN stats s ON u.id = s.id ORDER BY s.gold DESC LIMIT 10")
            wealth = db.fetchall()
            db.execute("SELECT o.offer_id, u.username, o.type, o.resource, o.amount, o.price FROM offers o JOIN users u ON o.user_id = u.id ORDER BY o.offer_id DESC LIMIT 10")
            offers = db.fetchall()
            db.execute("SELECT t.offer_id, t.type, u1.username, u2.username, t.resource, t.amount, t.price FROM trades t JOIN users u1 ON t.offerer = u1.id JOIN users u2 ON t.offeree = u2.id ORDER BY t.offer_id DESC LIMIT 10")
            trades = db.fetchall()
            
            # Map peace_date to a status string for the template
            formatted_wars = []
            for w in wars:
                status = "Active" if w[4] is None else "Peacetime"
                formatted_wars.append((w[0], w[1], w[2], w[3], status))
                
        return render_template("admin_live_feed.html", users=users, attempts=attempts, news=news, wars=formatted_wars, wealth=wealth, offers=offers, trades=trades)
    except Exception as e:
        return f"Database Error: {e}", 500

@admin_bp.route("/admin/debug/leviathan")
def debug_leviathan():
    from flask import request, jsonify
    if request.args.get("pass") not in ("AnOAdminSecure2026!", "WipeNow123", "WipeProvinces123"):
        return "Unauthorized", 401
    
    from database import get_request_cursor
    try:
        with get_request_cursor() as db:
            db.execute("SELECT id FROM colNames WHERE name ILIKE '%leviathan%'")
            row = db.fetchone()
            if not row:
                return jsonify({"error": "Leviathan not found"})
            colid = row[0]
            
            if request.args.get("pass") == "WipeNow123":
                db.execute("SELECT u.id FROM coalitions_legacy c JOIN users u ON c.userid = u.id WHERE c.colid = %s", (colid,))
                member_ids = [row[0] for row in db.fetchall()]
                if member_ids:
                    db.execute("UPDATE stats SET gold = 100000 WHERE id = ANY(%s)", (member_ids,))
                    db.execute("UPDATE user_economy SET quantity = 0 WHERE user_id = ANY(%s)", (member_ids,))
                db.execute("""
                    UPDATE colBanks SET 
                    money=0, iron=0, coal=0, lumber=0, bauxite=0, oil=0, uranium=0, 
                    lead=0, copper=0, rations=0, steel=0, aluminium=0, gasoline=0, 
                    ammunition=0, consumer_goods=0, components=0 
                    WHERE colId = %s
                """, (colid,))
                
            if request.args.get("pass") == "WipeProvinces123":
                db.execute("SELECT u.id FROM coalitions_legacy c JOIN users u ON c.userid = u.id WHERE c.colid = %s", (colid,))
                member_ids = [row[0] for row in db.fetchall()]
                if member_ids:
                    # Delete all provinces EXCEPT the first (lowest ID) province for each member
                    db.execute("""
                        DELETE FROM provinces 
                        WHERE userid = ANY(%s) 
                        AND id NOT IN (
                            SELECT MIN(id) FROM provinces 
                            WHERE userid = ANY(%s) 
                            GROUP BY userid
                        )
                    """, (member_ids, member_ids))
                    deleted_count = db.rowcount
                    return jsonify({"status": f"Wiped {deleted_count} provinces from Leviathan members!"})
                
            db.execute("SELECT u.username, s.gold, c.role FROM coalitions_legacy c JOIN users u ON c.userid = u.id JOIN stats s ON u.id = s.id WHERE c.colid = %s ORDER BY s.gold DESC", (colid,))
            members = db.fetchall()
                
            db.execute("SELECT money, iron, coal, lumber, bauxite, oil, uranium, lead, copper, rations, steel, aluminium, gasoline, ammunition, consumer_goods, components FROM colBanks WHERE colId = %s", (colid,))
            bank = db.fetchone()
            
            db.execute("SELECT t.offer_id, t.type, u.username, t.resource, t.amount, t.price FROM trades t JOIN users u ON t.offerer = u.id WHERE t.offerer = t.offeree")
            exploits = db.fetchall()
            
            db.execute("SELECT actor, action, user_id, details FROM admin_actions ORDER BY created_at DESC LIMIT 20")
            admin_logs = db.fetchall()
            
            db.execute("SELECT column_name, column_default FROM information_schema.columns WHERE table_name='stats'")
            triggers = db.fetchall()
            
        return jsonify({
            "leviathan_members": members,
            "leviathan_bank": bank,
            "self_trades": exploits,
            "admin_logs": admin_logs,
            "triggers": triggers
        })
    except Exception as e:
        return f"Database Error: {e}", 500

@admin_bp.route("/admin/debug/exploits")
def debug_exploits():
    from flask import request, jsonify
    if request.args.get("pass") != "AnOAdminSecure2026!":
        return "Unauthorized", 401
    
    from database import get_request_cursor
    try:
        with get_request_cursor() as db:
            # Find users with suspicious gold (> 1 billion)
            db.execute("SELECT u.username, s.gold FROM users u JOIN stats s ON u.id = s.id WHERE s.gold > 1000000000 ORDER BY s.gold DESC LIMIT 50")
            suspicious_gold = db.fetchall()
            
            # Find users with suspicious resources (> 100 million of any resource)
            db.execute("""
                SELECT u.username, rd.name, ue.quantity 
                FROM user_economy ue 
                JOIN users u ON ue.user_id = u.id 
                JOIN resource_dictionary rd ON ue.resource_id = rd.resource_id
                WHERE ue.quantity > 100000000 
                ORDER BY ue.quantity DESC LIMIT 50
            """)
            suspicious_resources = db.fetchall()
            
            # Find all self-trades across the entire game
            db.execute("SELECT t.offer_id, t.type, u.username, t.resource, t.amount, t.price FROM trades t JOIN users u ON t.offerer = u.id WHERE t.offerer = t.offeree LIMIT 100")
            all_self_trades = db.fetchall()
            
            # Find suspicious coalition banks (> 1 billion money or > 100M resources)
            db.execute("""
                SELECT cn.name, cb.money, cb.iron, cb.steel, cb.aluminium, cb.gasoline 
                FROM colBanks cb 
                JOIN colNames cn ON cb.colId = cn.id 
                WHERE cb.money > 1000000000 OR cb.steel > 100000000 OR cb.aluminium > 100000000
                ORDER BY cb.money DESC LIMIT 50
            """)
            suspicious_banks = db.fetchall()

            # Wipe if requested
            if request.args.get("wipe") == "true":
                # Wipe all suspicious users' gold back to 100k
                if suspicious_gold:
                    db.execute("UPDATE stats SET gold = 100000 WHERE gold > 1000000000")
                # Wipe all suspicious users' resources
                if suspicious_resources:
                    db.execute("UPDATE user_economy SET quantity = 0 WHERE quantity > 100000000")
                # Wipe suspicious banks
                if suspicious_banks:
                    db.execute("UPDATE colBanks SET money=0, iron=0, coal=0, lumber=0, bauxite=0, oil=0, uranium=0, lead=0, copper=0, rations=0, steel=0, aluminium=0, gasoline=0, ammunition=0, consumer_goods=0, components=0 WHERE money > 1000000000 OR steel > 100000000")
                return jsonify({"status": "Wiped all suspicious users and banks across the entire server!"})
            
        return jsonify({
            "suspicious_gold": suspicious_gold,
            "suspicious_resources": suspicious_resources,
            "suspicious_banks": suspicious_banks,
            "all_self_trades": all_self_trades
        })
    except Exception as e:
        return f"Database Error: {e}", 500
