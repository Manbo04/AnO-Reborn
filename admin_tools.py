from flask import render_template, request, session, redirect, flash

from database import get_db_cursor, invalidate_user_cache
from helpers import error, login_required


SUPER_ADMIN_USER_IDS = {1, 1215}


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

        db.execute(
            """
            SELECT aa.actor, aa.action, aa.user_id, aa.details, aa.created_at
            FROM admin_actions aa
            ORDER BY aa.created_at DESC
            LIMIT 30
            """
        )
        recent_actions = db.fetchall()

    return render_template(
        "admin_command_center.html",
        controlled_users=controlled_users,
        recent_actions=recent_actions,
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
                "INSERT INTO provinces (userId, provinceName) VALUES (%s, %s)",
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


def register_admin_tools_routes(app_instance):
    admin_home_wrapped = login_required(admin_command_center)
    admin_add_resource_wrapped = login_required(admin_add_resource)
    admin_add_provinces_wrapped = login_required(admin_add_provinces)
    admin_ban_user_wrapped = login_required(admin_ban_user)
    admin_unban_user_wrapped = login_required(admin_unban_user)
    admin_kick_user_wrapped = login_required(admin_kick_user)

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
