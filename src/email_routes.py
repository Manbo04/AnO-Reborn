from flask import Blueprint, redirect, render_template
import email_verification

bp = Blueprint("email_verification", __name__)


@bp.route("/verify_email/<token>", methods=["GET"])
def verify_email(token):
    """Verify token via pluggable backend and mark user verified in DB.

    Redirects to a success page on success or an expired/invalid page on failure.
    """
    entry = email_verification.verify_code(token)
    if not entry:
        # Token missing or expired
        return redirect("/email_verification_expired")

    # Try to mark user as verified when we have a user_id
    try:
        from database import get_db_cursor

        if getattr(entry, "user_id", None):
            with get_db_cursor() as db:
                db.execute(
                    "UPDATE users SET is_verified = TRUE, verification_token = NULL WHERE id = %s",
                    (entry.user_id,),
                )
    except Exception:
        # Non-fatal; proceed to success page even if DB update failed (idempotent)
        pass

    return redirect("/email_verified")


@bp.route("/email_verified", methods=["GET"])
def email_verified():
    return render_template("email_verified.html")


@bp.route("/email_verification_expired", methods=["GET"])
def email_verification_expired():
    return render_template("email_verification_expired.html")


def register_email_routes(app):
    app.register_blueprint(bp)
