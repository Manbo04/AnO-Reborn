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
            if users_table_has_column("auth_type"):
                user_cols += ", auth_type"
            if users_table_has_column("discord_id"):
                user_cols += ", discord_id"
            if users_table_has_column("recovery_key"):
                user_cols += ", recovery_key"
            if users_table_has_column("reset_count"):
                user_cols += ", reset_count"
            if users_table_has_column("show_discord"):
                user_cols += ", show_discord"
            if users_table_has_column("discord_username"):
                user_cols += ", discord_username"
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
    user.setdefault("discord_username", None)
    user.setdefault("show_discord", False)
    user.setdefault("auth_type", "normal")
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

    # Discord/Google-only accounts store the provider id in users.hash; the
    # page asks them for their nation name instead of a password they lack.
    has_password = True
    try:
        from app_core.auth.passwords import account_has_password

        with get_request_cursor() as db:
            db.execute("SELECT hash FROM users WHERE id=%s", (cId,))
            _row = db.fetchone()
        has_password = account_has_password(_row[0] if _row else None)
    except Exception:
        pass

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
        has_password=has_password,
    )


@bp.route("/account/reveal_email", methods=["POST"])
@login_required
def reveal_email():
    """Step-up confirmation before returning the account's real email --
    same shape as reset_account()/delete_own_account()/twofa_disable()
    (all require the current password, not just a valid session, per the
    2026-09-05 incident where a stolen session cookie alone was enough to
    trigger destructive actions). The account page previously showed
    mask_email(user.email) to anyone with a valid session; per Dede's
    request this closes that too -- a leaked/stolen session cookie
    (exactly the class of bug the cache_response fix closed) should not
    be enough to read the account's real email either. AJAX endpoint
    (not a page route): the account page never embeds the real email in
    its initial HTML anymore, only after this call succeeds.
    """
    from app_core.auth.passwords import confirm_identity

    cId = session["user_id"]
    confirm_password = request.form.get("confirm_password")
    if not confirm_password:
        return {"ok": False, "error": "Confirm your password to view your email"}, 400

    with get_request_cursor() as db:
        db.execute("SELECT hash, email, username FROM users WHERE id=%s", (cId,))
        row = db.fetchone()
    if not row or not row[0]:
        return {"ok": False, "error": "Account data is missing. Please contact support."}, 500

    # Discord/Google-only accounts confirm with their nation name instead.
    if not confirm_identity(row[0], row[2], confirm_password):
        return {"ok": False, "error": "Incorrect password"}, 400

    return {"ok": True, "email": row[1]}


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
    from app_core.auth import totp
    from app_core.auth.passwords import account_has_password, password_matches

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
    if account_has_password(row[0]):
        password_ok = password_matches(row[0], confirm_password)
    else:
        # Discord/Google-only accounts have no password; typing the nation
        # name would be weaker than the factor being removed, so they prove
        # it with a current authenticator code instead.
        password_ok = totp.verify_login_code(cId, confirm_password.strip())
    if not password_ok:
        return error(400, "Confirm your password to disable two-factor authentication")

    with get_request_cursor() as db:
        totp.disable_2fa(db, cId)

    flash("Two-factor authentication has been disabled.")
    return redirect("/account")


@bp.route("/account/toggle_show_discord", methods=["POST"])
@login_required
def toggle_show_discord():
    cId = session["user_id"]
    with get_request_cursor() as db:
        try:
            db.execute("SELECT discord_id, show_discord FROM users WHERE id=%s", (cId,))
            row = db.fetchone()
        except Exception:
            rollback_db_cursor(db)
            row = None

        if not row:
            flash("Account not found.")
            return redirect("/account")

        discord_id = row[0]
        current_show = bool(row[1]) if len(row) > 1 and row[1] is not None else False
        if not discord_id:
            flash("You must link a Discord account first before displaying your Discord name on your nation page.")
            return redirect("/account")

        new_val = not current_show
        if "show_discord" in request.form:
            form_val = request.form.get("show_discord")
            if form_val in ("true", "1", "on"):
                new_val = True
            elif form_val in ("false", "0", "off"):
                new_val = False
        elif request.form.get("form_submitted"):
            new_val = False

        if users_table_has_column("show_discord"):
            try:
                db.execute("UPDATE users SET show_discord=%s WHERE id=%s", (new_val, cId))
                if new_val:
                    flash("Your Discord name will now be shown on your nation page.")
                else:
                    flash("Your Discord name is now hidden from your nation page.")
            except Exception:
                rollback_db_cursor(db)
                flash("Could not update Discord visibility setting.")
        else:
            flash("Discord visibility setting is not available right now.")

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
        user_id = session.get("user_id")
        session.clear()

        # Force-disconnect any live Socket.IO connections for this user.
        # extensions.py's manage_session=False means a connection's Flask
        # session is frozen to whatever cookie was present at the original
        # connect handshake (documented python-socketio behavior) -- a tab
        # that stays connected across this logout would otherwise keep
        # sending/receiving chat events as the now-logged-out user until it
        # happens to reconnect on its own. close_room() drops every socket
        # in that user's personal room (joined on connect, see
        # app_core/chat/routes.py); Socket.IO's client auto-reconnects by
        # default, which re-establishes the connection against the
        # browser's *current* cookie -- the new user if one logged back in
        # on the same tab, or none if genuinely logged out.
        try:
            from flask_socketio import close_room

            # Must pass namespace explicitly: close_room()'s default lookup
            # reads flask.request.namespace, an attribute Flask-SocketIO
            # only sets while dispatching an actual socket event -- on a
            # plain HTTP route like this one it doesn't exist and would
            # raise AttributeError every time. This app registers no
            # custom namespaces (join_room/emit throughout use the
            # implicit default), so "/" is always correct here.
            close_room(f"user_{user_id}", namespace="/")
        except Exception:
            logging.getLogger(__name__).exception(
                "logout: failed to close socketio room for user_id=%s", user_id
            )
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
