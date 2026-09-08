import re

from flask import Blueprint, request, render_template, session, redirect, flash, url_for

from helpers import login_required, is_theme_v2_enabled
from database import get_request_cursor

from .repositories import activate_treaty, set_treaty_rejected, set_treaty_cancelled
from .services import list_treaties, offer_treaty as offer_treaty_service, TREATY_TYPE_LABELS
from app_core.market.repositories import get_username
from app_core.world_affairs.services import log_event

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


def _safe_next_or_treaties(next_url):
    """Only ever redirect back to a nation profile or the treaties inbox -
    never an arbitrary external/open-redirect target."""
    if next_url and re.fullmatch(r"/country/id=\d+", next_url):
        return next_url
    return url_for("treaties.view_treaties")


@bp.route("/treaties/offer", methods=["POST"])
@login_required
def offer_treaty():
    sender_id = session.get("user_id")
    recipient_name = request.form.get("recipient_name")
    treaty_type = request.form.get("treaty_type")
    destination = _safe_next_or_treaties(request.form.get("next"))

    with get_request_cursor() as db:
        ok, error, category = offer_treaty_service(db, sender_id, recipient_name, treaty_type)

    if not ok:
        flash(error, category)
        return redirect(destination)

    flash("Treaty offer sent!", "success")
    return redirect(destination)


@bp.route("/treaties/accept/<int:treaty_id>", methods=["POST"])
@login_required
def accept_treaty(treaty_id):
    user_id = session.get("user_id")
    with get_request_cursor() as db:
        row = activate_treaty(db, treaty_id, user_id)
        if row:
            treaty_type, sender_id, recipient_id = row
            sender_name = get_username(db, sender_id) or "A nation"
            recipient_name = get_username(db, recipient_id) or "a nation"
            label = TREATY_TYPE_LABELS.get(treaty_type, treaty_type)
            log_event(
                db, "treaty",
                f"{sender_name} and {recipient_name} have formed a {label}.",
                actor_id=sender_id, target_id=recipient_id,
            )
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
