import ast

from flask import jsonify, render_template, request, session, redirect, flash

from database import get_db_cursor, invalidate_user_cache
from helpers import error, login_required
from variables import RESOURCES


SUPER_ADMIN_USER_IDS = {1, 16, 1215, 69696969}


def _admin_only_guard():
    if session.get("user_id") not in SUPER_ADMIN_USER_IDS:
        allowed = ", ".join(str(uid) for uid in sorted(SUPER_ADMIN_USER_IDS))
        return error(
            403,
            f"This command center is restricted to nation IDs: {allowed}.",
        )
    return None


def _ensure_admin_tables(db):
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_actions (
            id SERIAL PRIMARY KEY,
            actor INTEGER NOT NULL,
            action TEXT NOT NULL,
            user_id INTEGER,
            details TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_user_controls (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            is_banned BOOLEAN NOT NULL DEFAULT FALSE,
            ban_reason TEXT,
            kick_pending BOOLEAN NOT NULL DEFAULT FALSE,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS game_economy_snapshots (
            id SERIAL PRIMARY KEY,
            snapshot_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            resource_name TEXT NOT NULL,
            total_quantity BIGINT NOT NULL DEFAULT 0,
            player_count INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_economy_snapshots_time_resource
        ON game_economy_snapshots (resource_name, snapshot_time DESC)
        """
    )


def _log_admin_action(db, actor, action, user_id, details):
    db.execute(
        (
            "INSERT INTO admin_actions (actor, action, user_id, details) "
            "VALUES (%s, %s, %s, %s)"
        ),
        (actor, action, user_id, details),
    )


def _validate_target_user(db, target_user_id):
    db.execute("SELECT id, username FROM users WHERE id=%s", (target_user_id,))
    return db.fetchone()


def admin_command_center():
    denied = _admin_only_guard()
    if denied:
        return denied

    with get_db_cursor() as db:
        _ensure_admin_tables(db)

        db.execute(
            """
            SELECT u.id, u.username,
                   COALESCE(c.is_banned, FALSE) AS is_banned,
                   COALESCE(c.kick_pending, FALSE) AS kick_pending,
                   COALESCE(c.ban_reason, '') AS ban_reason
            FROM users u
            LEFT JOIN admin_user_controls c ON c.user_id = u.id
            WHERE COALESCE(c.is_banned, FALSE) = TRUE
               OR COALESCE(c.kick_pending, FALSE) = TRUE
            ORDER BY u.id ASC
            """
        )
        controlled_users = db.fetchall()

        # Fetch recent actions with actor and target usernames resolved
        db.execute(
            """
            SELECT aa.actor,
                   COALESCE(actor_u.username, aa.actor, 'System') AS actor_name,
                   aa.action,
                   aa.user_id AS target_id,
                   COALESCE(target_u.username, '—') AS target_name,
                   aa.details,
                   aa.created_at
            FROM admin_actions aa
            LEFT JOIN users actor_u
                ON (aa.actor ~ '^[0-9]+$' AND actor_u.id = aa.actor::integer)
                OR (aa.actor !~ '^[0-9]+$' AND actor_u.username = aa.actor)
            LEFT JOIN users target_u ON target_u.id = aa.user_id
            ORDER BY aa.created_at DESC
            LIMIT 50
            """
        )
        recent_actions = db.fetchall()

        # New accounts in the last 7 days
        db.execute(
            """
            SELECT date, COUNT(*) AS cnt
            FROM users
            WHERE date::date >= CURRENT_DATE - INTERVAL '6 days'
            GROUP BY date
            ORDER BY date DESC
            """
        )
        new_accounts_by_day = db.fetchall()
        new_accounts_total = sum(row[1] for row in new_accounts_by_day)

    # Parse details into human-readable format
    parsed_actions = []
    for row in recent_actions:
        actor_id, actor_name, action, target_id, target_name, raw_details, ts = row
        details_parts = _parse_details(raw_details or "")
        parsed_actions.append(
            {
                "actor_id": actor_id,
                "actor_name": actor_name,
                "action": _format_action(action),
                "action_raw": action,
                "target_id": target_id,
                "target_name": target_name,
                "details": details_parts,
                "time": ts,
            }
        )

    return render_template(
        "admin_command_center.html",
        controlled_users=controlled_users,
        recent_actions=parsed_actions,
        new_accounts_by_day=new_accounts_by_day,
        new_accounts_total=new_accounts_total,
    )


def admin_add_resource():
    denied = _admin_only_guard()
    if denied:
        return denied

    actor = session["user_id"]

    try:
        target_user_id = int(request.form.get("target_user_id", "0"))
        amount = int(request.form.get("amount", "0"))
    except ValueError:
        return error(400, "Invalid user ID or amount")

    resource = (request.form.get("resource") or "").strip().lower()

    if target_user_id <= 0:
        return error(400, "Target user ID must be positive")
    if amount <= 0:
        return error(400, "Amount must be positive")
    if not resource:
        return error(400, "Resource is required")

    with get_db_cursor() as db:
        _ensure_admin_tables(db)

        target_row = _validate_target_user(db, target_user_id)
        if not target_row:
            return error(404, "Target user not found")

        if resource in ["money", "gold"]:
            db.execute(
                "UPDATE stats SET gold = gold + %s WHERE id = %s",
                (amount, target_user_id),
            )

            db.execute(
                "SELECT resource_id FROM resource_dictionary WHERE name='money'",
            )
            money_row = db.fetchone()
            if money_row:
                money_resource_id = money_row[0]
                db.execute(
                    """
                    INSERT INTO user_economy (user_id, resource_id, quantity)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id, resource_id)
                    DO UPDATE SET quantity = user_economy.quantity + EXCLUDED.quantity
                    """,
                    (target_user_id, money_resource_id, amount),
                )

            _log_admin_action(
                db,
                actor,
                "admin_add_resource",
                target_user_id,
                f"resource=money amount={amount}",
            )
        else:
            db.execute(
                (
                    "SELECT resource_id FROM resource_dictionary "
                    "WHERE name=%s AND is_active=TRUE"
                ),
                (resource,),
            )
            resource_row = db.fetchone()
            if not resource_row:
                return error(400, "Unknown or inactive resource")

            resource_id = resource_row[0]
            db.execute(
                """
                INSERT INTO user_economy (user_id, resource_id, quantity)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, resource_id)
                DO UPDATE SET quantity = user_economy.quantity + EXCLUDED.quantity
                """,
                (target_user_id, resource_id, amount),
            )

            _log_admin_action(
                db,
                actor,
                "admin_add_resource",
                target_user_id,
                f"resource={resource} amount={amount}",
            )

    try:
        invalidate_user_cache(target_user_id)
    except Exception:
        pass

    flash(f"Added {amount} {resource} to user {target_user_id}")
    return redirect("/admin/command-center")


def admin_add_provinces():
    denied = _admin_only_guard()
    if denied:
        return denied

    actor = session["user_id"]

    try:
        target_user_id = int(request.form.get("target_user_id", "0"))
        amount = int(request.form.get("amount", "0"))
    except ValueError:
        return error(400, "Invalid user ID or amount")

    if target_user_id <= 0:
        return error(400, "Target user ID must be positive")
    if amount <= 0 or amount > 50:
        return error(400, "Province amount must be between 1 and 50")

    with get_db_cursor() as db:
        _ensure_admin_tables(db)

        target_row = _validate_target_user(db, target_user_id)
        if not target_row:
            return error(404, "Target user not found")

        db.execute(
            "SELECT COALESCE(MAX(id), 0) FROM provinces WHERE userId=%s",
            (target_user_id,),
        )
        current_max = db.fetchone()[0]

        for idx in range(1, amount + 1):
            db.execute(
                "INSERT INTO provinces (userId, provinceName, pop_children) "
                "VALUES (%s, %s, 1000000)",
                (target_user_id, f"Admin Province {current_max + idx}"),
            )

        _log_admin_action(
            db,
            actor,
            "admin_add_provinces",
            target_user_id,
            f"amount={amount}",
        )

    try:
        invalidate_user_cache(target_user_id)
    except Exception:
        pass

    flash(f"Added {amount} province(s) to user {target_user_id}")
    return redirect("/admin/command-center")


def admin_ban_user():
    denied = _admin_only_guard()
    if denied:
        return denied

    actor = session["user_id"]

    try:
        target_user_id = int(request.form.get("target_user_id", "0"))
    except ValueError:
        return error(400, "Invalid user ID")

    if target_user_id <= 0:
        return error(400, "Target user ID must be positive")
    if target_user_id in SUPER_ADMIN_USER_IDS:
        return error(400, "Cannot ban a privileged admin nation")

    reason = (request.form.get("reason") or "No reason provided").strip()

    with get_db_cursor() as db:
        _ensure_admin_tables(db)

        target_row = _validate_target_user(db, target_user_id)
        if not target_row:
            return error(404, "Target user not found")

        db.execute(
            """
            INSERT INTO admin_user_controls (
                user_id, is_banned, ban_reason, kick_pending, updated_at
            )
            VALUES (%s, TRUE, %s, TRUE, NOW())
            ON CONFLICT (user_id)
            DO UPDATE SET is_banned=TRUE,
                          ban_reason=EXCLUDED.ban_reason,
                          kick_pending=TRUE,
                          updated_at=NOW()
            """,
            (target_user_id, reason),
        )

        _log_admin_action(
            db,
            actor,
            "admin_ban_user",
            target_user_id,
            f"reason={reason}",
        )

    flash(f"Banned user {target_user_id}")
    return redirect("/admin/command-center")


def admin_unban_user():
    denied = _admin_only_guard()
    if denied:
        return denied

    actor = session["user_id"]

    try:
        target_user_id = int(request.form.get("target_user_id", "0"))
    except ValueError:
        return error(400, "Invalid user ID")

    if target_user_id <= 0:
        return error(400, "Target user ID must be positive")

    with get_db_cursor() as db:
        _ensure_admin_tables(db)

        target_row = _validate_target_user(db, target_user_id)
        if not target_row:
            return error(404, "Target user not found")

        db.execute(
            """
            INSERT INTO admin_user_controls (
                user_id, is_banned, ban_reason, kick_pending, updated_at
            )
            VALUES (%s, FALSE, NULL, FALSE, NOW())
            ON CONFLICT (user_id)
            DO UPDATE SET is_banned=FALSE,
                          ban_reason=NULL,
                          kick_pending=FALSE,
                          updated_at=NOW()
            """,
            (target_user_id,),
        )

        _log_admin_action(
            db,
            actor,
            "admin_unban_user",
            target_user_id,
            "",
        )

    flash(f"Unbanned user {target_user_id}")
    return redirect("/admin/command-center")


def admin_kick_user():
    denied = _admin_only_guard()
    if denied:
        return denied

    actor = session["user_id"]

    try:
        target_user_id = int(request.form.get("target_user_id", "0"))
    except ValueError:
        return error(400, "Invalid user ID")

    if target_user_id <= 0:
        return error(400, "Target user ID must be positive")
    if target_user_id in SUPER_ADMIN_USER_IDS:
        return error(400, "Cannot kick a privileged admin nation")

    reason = (request.form.get("reason") or "No reason provided").strip()

    with get_db_cursor() as db:
        _ensure_admin_tables(db)

        target_row = _validate_target_user(db, target_user_id)
        if not target_row:
            return error(404, "Target user not found")

        db.execute(
            """
            INSERT INTO admin_user_controls (
                user_id, is_banned, ban_reason, kick_pending, updated_at
            )
            VALUES (%s, FALSE, NULL, TRUE, NOW())
            ON CONFLICT (user_id)
            DO UPDATE SET kick_pending=TRUE,
                          updated_at=NOW()
            """,
            (target_user_id,),
        )

        _log_admin_action(
            db,
            actor,
            "admin_kick_user",
            target_user_id,
            f"reason={reason}",
        )

    flash(f"Kick queued for user {target_user_id}")
    return redirect("/admin/command-center")


# ---------------------------------------------------------------------------
# Detail parsing & formatting helpers
# ---------------------------------------------------------------------------

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


def _format_action(action):
    label, _ = _ACTION_LABELS.get(action, (action.replace("_", " ").title(), "muted"))
    return label


def _action_badge_class(action):
    _, cls = _ACTION_LABELS.get(action, (action, "muted"))
    return cls


def _parse_details(raw):
    """Turn 'resource=money amount=500' or dict-like strings into readable parts."""
    if not raw:
        return []

    # psycopg2 auto-deserializes JSONB columns into dicts/lists
    if isinstance(raw, (dict, list)):
        return _flatten_dict(raw)

    # Handle dict-repr strings like "{'province': {'id': 820, ...}}"
    if raw.startswith("{") or raw.startswith("("):
        try:
            obj = ast.literal_eval(raw)
            return _flatten_dict(obj)
        except Exception:
            return [("Details", raw)]

    # Handle key=value pairs
    parts = []
    for token in raw.split():
        if "=" in token:
            key, _, val = token.partition("=")
            parts.append((key.replace("_", " ").title(), val))
        else:
            parts.append(("Info", token))
    return parts


def _flatten_dict(obj, prefix=""):
    """Flatten a nested dict into a list of (label, value) pairs for display."""
    parts = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            label = (
                f"{prefix}{k}".replace("_", " ").title()
                if prefix
                else str(k).replace("_", " ").title()
            )
            if isinstance(v, dict):
                parts.extend(_flatten_dict(v, f"{k}."))
            elif isinstance(v, (list, tuple)):
                parts.append((label, ", ".join(str(i) for i in v)))
            else:
                parts.append((label, str(v)))
    else:
        parts.append((prefix.rstrip(".").title() or "Value", str(obj)))
    return parts


# ---------------------------------------------------------------------------
# Economy dashboard & snapshots
# ---------------------------------------------------------------------------


def take_economy_snapshot():
    """Capture current total of each resource across all players.

    Called by Celery beat (hourly) and can also be triggered manually.
    """
    with get_db_cursor() as db:
        _ensure_admin_tables(db)

        # Gold from stats table
        db.execute("SELECT COALESCE(SUM(gold), 0), COUNT(*) FROM stats WHERE gold > 0")
        gold_row = db.fetchone()
        db.execute(
            """
            INSERT INTO game_economy_snapshots
                (resource_name, total_quantity, player_count)
            VALUES ('gold', %s, %s)
            """,
            (gold_row[0], gold_row[1]),
        )

        # All resources from user_economy
        db.execute(
            """
            SELECT rd.name,
                   COALESCE(SUM(ue.quantity), 0),
                   COUNT(*) FILTER (WHERE ue.quantity > 0)
            FROM resource_dictionary rd
            LEFT JOIN user_economy ue ON ue.resource_id = rd.resource_id
            WHERE rd.is_active = TRUE
              AND rd.name != 'money'
            GROUP BY rd.name
            ORDER BY rd.name
            """
        )
        for row in db.fetchall():
            db.execute(
                """
                INSERT INTO game_economy_snapshots
                    (resource_name, total_quantity, player_count)
                VALUES (%s, %s, %s)
                """,
                (row[0], row[1], row[2]),
            )

        # Prune snapshots older than 90 days
        db.execute(
            """
            DELETE FROM game_economy_snapshots
            WHERE snapshot_time < NOW() - INTERVAL '90 days'
            """
        )


def admin_economy_dashboard():
    """Render the economy monitoring page with resource graphs."""
    denied = _admin_only_guard()
    if denied:
        return denied

    with get_db_cursor() as db:
        _ensure_admin_tables(db)

        # Current totals (latest snapshot per resource)
        db.execute(
            """
            SELECT DISTINCT ON (resource_name)
                   resource_name, total_quantity, player_count, snapshot_time
            FROM game_economy_snapshots
            ORDER BY resource_name, snapshot_time DESC
            """
        )
        current_totals = db.fetchall()

        # Check how many snapshots we have
        db.execute("SELECT COUNT(*) FROM game_economy_snapshots")
        snapshot_count = db.fetchone()[0]

    resource_list = ["gold"] + RESOURCES

    return render_template(
        "admin_economy.html",
        current_totals=current_totals,
        snapshot_count=snapshot_count,
        resource_list=resource_list,
    )


def admin_economy_api():
    """JSON API returning snapshot time-series for Chart.js."""
    denied = _admin_only_guard()
    if denied:
        return denied

    resource = request.args.get("resource", "gold").strip().lower()
    days = min(int(request.args.get("days", "7")), 90)

    valid_resources = {"gold"} | set(RESOURCES)
    if resource not in valid_resources:
        return jsonify({"error": "Unknown resource"}), 400

    with get_db_cursor() as db:
        _ensure_admin_tables(db)

        db.execute(
            """
            SELECT snapshot_time, total_quantity, player_count
            FROM game_economy_snapshots
            WHERE resource_name = %s
              AND snapshot_time > NOW() - make_interval(days => %s)
            ORDER BY snapshot_time ASC
            """,
            (resource, days),
        )
        rows = db.fetchall()

    data = {
        "resource": resource,
        "labels": [r[0].strftime("%m/%d %H:%M") for r in rows],
        "totals": [int(r[1]) for r in rows],
        "player_counts": [int(r[2]) for r in rows],
    }
    return jsonify(data)


def admin_trigger_snapshot():
    """Manually trigger an economy snapshot."""
    denied = _admin_only_guard()
    if denied:
        return denied

    take_economy_snapshot()
    flash("Economy snapshot taken successfully.")
    return redirect("/admin/command-center/economy")


def register_admin_tools_routes(app_instance):
    admin_home_wrapped = login_required(admin_command_center)
    admin_add_resource_wrapped = login_required(admin_add_resource)
    admin_add_provinces_wrapped = login_required(admin_add_provinces)
    admin_ban_user_wrapped = login_required(admin_ban_user)
    admin_unban_user_wrapped = login_required(admin_unban_user)
    admin_kick_user_wrapped = login_required(admin_kick_user)
    admin_economy_wrapped = login_required(admin_economy_dashboard)
    admin_economy_api_wrapped = login_required(admin_economy_api)
    admin_snapshot_wrapped = login_required(admin_trigger_snapshot)

    app_instance.add_url_rule(
        "/admin/command-center",
        "admin_command_center",
        admin_home_wrapped,
        methods=["GET"],
    )
    app_instance.add_url_rule(
        "/admin/command-center/add-resource",
        "admin_add_resource",
        admin_add_resource_wrapped,
        methods=["POST"],
    )
    app_instance.add_url_rule(
        "/admin/command-center/add-provinces",
        "admin_add_provinces",
        admin_add_provinces_wrapped,
        methods=["POST"],
    )
    app_instance.add_url_rule(
        "/admin/command-center/ban-user",
        "admin_ban_user",
        admin_ban_user_wrapped,
        methods=["POST"],
    )
    app_instance.add_url_rule(
        "/admin/command-center/unban-user",
        "admin_unban_user",
        admin_unban_user_wrapped,
        methods=["POST"],
    )
    app_instance.add_url_rule(
        "/admin/command-center/kick-user",
        "admin_kick_user",
        admin_kick_user_wrapped,
        methods=["POST"],
    )
    app_instance.add_url_rule(
        "/admin/command-center/economy",
        "admin_economy_dashboard",
        admin_economy_wrapped,
        methods=["GET"],
    )
    app_instance.add_url_rule(
        "/admin/command-center/economy/api",
        "admin_economy_api",
        admin_economy_api_wrapped,
        methods=["GET"],
    )
    app_instance.add_url_rule(
        "/admin/command-center/economy/snapshot",
        "admin_trigger_snapshot",
        admin_snapshot_wrapped,
        methods=["POST"],
    )

    # Register Jinja filter for action badge classes
    app_instance.jinja_env.globals["action_badge_class"] = _action_badge_class
