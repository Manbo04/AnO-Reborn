from flask import Blueprint, render_template, session, redirect
from helpers import login_required, error
from database import get_request_cursor, rollback_db_cursor, users_table_has_column
from psycopg2.extras import RealDictCursor

bp = Blueprint('auth_bp', __name__)

@bp.route("/account", methods=["GET"])
@login_required
def account():
    from datetime import timezone
    cId = session["user_id"]
    user = None
    has_recovery_key = False
    with get_request_cursor(cursor_factory=RealDictCursor) as db:
        try:
            user_cols = "username, email, date"
            if users_table_has_column("discord_id"):
                user_cols += ", discord_id"
            if users_table_has_column("recovery_key"):
                user_cols += ", recovery_key"
            db.execute(f"SELECT {user_cols} FROM users WHERE id=%s", (cId,))
            row = db.fetchone()
            if row:
                user = dict(row)
                if "recovery_key" in user:
                    has_recovery_key = bool(user.get("recovery_key"))
                    user.pop("recovery_key", None)
        except Exception:
            rollback_db_cursor(db)
            try:
                db.execute("SELECT username, email, date FROM users WHERE id=%s", (cId,))
                row = db.fetchone()
                if row:
                    user = dict(row)
                    user.setdefault("discord_id", None)
            except Exception:
                rollback_db_cursor(db)

    if not user:
        return error(404, "Account not found")
    user.setdefault("discord_id", None)

    discord_bot_link = None
    discord_link_ttl_minutes = 30
    try:
        from bot_api import CODE_TTL_MINUTES, get_active_discord_link_code
        discord_link_ttl_minutes = CODE_TTL_MINUTES
        discord_bot_link = get_active_discord_link_code(cId)
    except Exception: pass

    if discord_bot_link:
        exp = discord_bot_link.get("expires_at")
        if exp is not None:
            if getattr(exp, "tzinfo", None) is None: exp = exp.replace(tzinfo=timezone.utc)
            discord_bot_link["expires_display"] = exp.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        else: discord_bot_link["expires_display"] = "soon"

    referral_dashboard = None
    try:
        from app_core.referrals.service import get_referral_dashboard

        with get_request_cursor() as db:
            referral_dashboard = get_referral_dashboard(db, cId)
    except Exception:
        pass

    return render_template(
        "account.html",
        user=user,
        discord_bot_link=discord_bot_link,
        discord_link_ttl_minutes=discord_link_ttl_minutes,
        has_recovery_key=has_recovery_key,
        referral_dashboard=referral_dashboard,
    )

@bp.route("/logout")
def logout():
    if session.get("user_id") is not None: session.clear()
    return redirect("/")

@bp.route("/forgot_password", methods=["GET"])
def forget_password():
    try:
        from email_utils import is_email_configured
        email_enabled = is_email_configured()
    except Exception:
        email_enabled = False
    recovery_key_available = users_table_has_column("recovery_key")
    return render_template(
        "forgot_password.html",
        email_enabled=email_enabled,
        recovery_key_available=recovery_key_available,
    )
