from flask import Blueprint, render_template, session, redirect, request, flash, make_response
from helpers import login_required, error, is_theme_v2_enabled, session_cookie_fingerprint
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
            if users_table_has_column("reset_count"):
                user_cols += ", reset_count"
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
    reset_count = user.pop("reset_count", 0) or 0

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

    from app_core.auth import totp

    template = "account_v2.html" if is_theme_v2_enabled("account") else "account.html"
    return render_template(
        template,
        user=user,
        discord_bot_link=discord_bot_link,
        discord_link_ttl_minutes=discord_link_ttl_minutes,
        has_recovery_key=has_recovery_key,
        has_2fa_enabled=totp.has_2fa_enabled(cId),
        referral_dashboard=referral_dashboard,
        reset_is_first=(reset_count == 0),
    )


@bp.route("/account/2fa/setup", methods=["GET"])
@login_required
def twofa_setup():
    from app_core.auth import totp

    cId = session["user_id"]
    if totp.has_2fa_enabled(cId):
        flash("Two-factor authentication is already enabled. Disable it first to re-enroll.")
        return redirect("/account")

    try:
        with get_request_cursor() as db:
            secret = totp.start_or_resume_enrollment(db, cId)
    except totp.TwoFactorUnavailableError:
        flash("Two-factor authentication is temporarily unavailable. Please try again later.")
        return redirect("/account")

    with get_request_cursor() as db:
        db.execute("SELECT username FROM users WHERE id=%s", (cId,))
        row = db.fetchone()
    account_label = row[0] if row else f"user-{cId}"

    qr_data_uri = totp.build_qr_data_uri(secret, account_label)

    resp = make_response(
        render_template("twofa_setup.html", secret=secret, qr_data_uri=qr_data_uri)
    )
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.route("/account/2fa/confirm", methods=["POST"])
@login_required
def twofa_confirm():
    from app_core.auth import totp

    cId = session["user_id"]
    code = request.form.get("code", "")

    try:
        with get_request_cursor() as db:
            backup_codes = totp.confirm_enrollment(db, cId, code)
    except totp.TwoFactorUnavailableError:
        flash("Two-factor authentication is temporarily unavailable. Please try again later.")
        return redirect("/account")

    if backup_codes is None:
        flash("Invalid code. Please try again.")
        return redirect("/account/2fa/setup")

    resp = make_response(
        render_template("twofa_backup_codes.html", backup_codes=backup_codes)
    )
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.route("/account/2fa/disable", methods=["POST"])
@login_required
def twofa_disable():
    import bcrypt
    from app_core.auth import totp

    cId = session["user_id"]

    # Step-up confirmation, identical shape to countries.py::reset_account()'s
    # confirm_password gate -- a stolen session cookie alone must not be
    # enough to turn off the second factor protecting the account.
    confirm_password = request.form.get("confirm_password")
    if not confirm_password:
        return error(400, "Confirm your password to disable two-factor authentication")

    with get_request_cursor() as db:
        db.execute("SELECT hash FROM users WHERE id=%s", (cId,))
        row = db.fetchone()
    if not row or not row[0]:
        return error(500, "Account data is missing. Please contact support.")
    try:
        password_ok = bcrypt.checkpw(
            confirm_password.encode("utf-8"), row[0].encode("utf-8")
        )
    except Exception:
        password_ok = False
    if not password_ok:
        return error(400, "Confirm your password to disable two-factor authentication")

    with get_request_cursor() as db:
        totp.disable_2fa(db, cId)

    flash("Two-factor authentication has been disabled.")
    return redirect("/account")


@bp.route("/logout")
def logout():
    # TEMPORARY diagnostic (ticket-0028, 2026-09-04): log the pre-clear
    # cookie fingerprint + user_id so a recurrence can show whether a later
    # request's session cookie fingerprint matches this one (client never
    # applied the clear) or differs (server-side session mixup instead).
    # See helpers.session_cookie_fingerprint for details; remove once
    # confirmed or stale.
    if session.get("user_id") is not None:
        import logging
        logging.getLogger(__name__).info(
            "logout: user_id=%s cookie_fp=%s ip=%s",
            session.get("user_id"),
            session_cookie_fingerprint(),
            request.remote_addr,
        )
        session.clear()
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
