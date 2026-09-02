from flask import Blueprint, request, render_template, session, redirect, flash, url_for

from helpers import login_required, is_theme_v2_enabled
from database import get_request_cursor

from .repositories import activate_treaty, set_treaty_rejected, set_treaty_cancelled
from .services import list_treaties, offer_treaty as offer_treaty_service

bp = Blueprint("treaties", __name__)


@bp.route("/treaties", methods=["GET"])
@login_required
def view_treaties():
    user_id = session.get("user_id")
    with get_request_cursor() as db:
        active_treaties, incoming_treaties, outgoing_treaties = list_treaties(db, user_id)

    template = "treaty_v2.html" if is_theme_v2_enabled("treaties") else "treaty.html"
    return render_template(
        template,
        active_treaties=active_treaties,
        incoming_treaties=incoming_treaties,
        outgoing_treaties=outgoing_treaties,
        user_id=user_id,
    )


@bp.route("/treaties/offer", methods=["POST"])
@login_required
def offer_treaty():
    sender_id = session.get("user_id")
    recipient_name = request.form.get("recipient_name")
    treaty_type = request.form.get("treaty_type")

    with get_request_cursor() as db:
        ok, error, category = offer_treaty_service(db, sender_id, recipient_name, treaty_type)

    if not ok:
        flash(error, category)
        return redirect(url_for("treaties.view_treaties"))

    flash("Treaty offer sent!", "success")
    return redirect(url_for("treaties.view_treaties"))


@bp.route("/treaties/accept/<int:treaty_id>", methods=["POST"])
@login_required
def accept_treaty(treaty_id):
    user_id = session.get("user_id")
    with get_request_cursor() as db:
        activate_treaty(db, treaty_id, user_id)
    flash("Treaty accepted!", "success")
    return redirect(url_for("treaties.view_treaties"))


@bp.route("/treaties/reject/<int:treaty_id>", methods=["POST"])
@login_required
def reject_treaty(treaty_id):
    user_id = session.get("user_id")
    with get_request_cursor() as db:
        set_treaty_rejected(db, treaty_id, user_id)
    flash("Treaty rejected.", "info")
    return redirect(url_for("treaties.view_treaties"))


@bp.route("/treaties/cancel/<int:treaty_id>", methods=["POST"])
@login_required
def cancel_treaty(treaty_id):
    user_id = session.get("user_id")
    with get_request_cursor() as db:
        set_treaty_cancelled(db, treaty_id, user_id)
    flash("Treaty cancelled.", "info")
    return redirect(url_for("treaties.view_treaties"))
