from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from helpers import redirect_back

from database import get_request_cursor, invalidate_user_cache
from helpers import login_required

from . import services

bp = Blueprint("currency_market", __name__)


def _back():
    issuer = request.form.get("back_issuer", "")
    if issuer.isdigit():
        return redirect(url_for("currency_market.currency_market", currency=issuer))
    return redirect_back(url_for("currency_market.currency_market"))


@bp.route("/currency_market")
@login_required
def currency_market():
    user_id = session["user_id"]
    issuer = request.args.get("currency", "")
    issuer_filter = int(issuer) if issuer.isdigit() else None
    with get_request_cursor() as db:
        data = services.get_page_data(db, user_id, issuer_filter)
    return render_template("currency_market.html", cId=user_id, **data)


@bp.route("/currency_market/offer", methods=["POST"])
@login_required
def create_offer():
    user_id = session["user_id"]
    issuer = request.form.get("issuer_id", "")
    if not issuer.isdigit():
        flash("Pick a currency.", "danger")
        return _back()
    with get_request_cursor() as db:
        ok, msg, cat = services.create_offer(
            db, user_id, int(issuer), request.form.get("type"),
            request.form.get("amount"), request.form.get("price"),
        )
    flash(msg, cat)
    if ok:
        invalidate_user_cache(user_id)
    return _back()


@bp.route("/currency_market/cancel/<int:offer_id>", methods=["POST"])
@login_required
def cancel_offer(offer_id):
    user_id = session["user_id"]
    with get_request_cursor() as db:
        ok, msg, cat = services.cancel_offer(db, user_id, offer_id)
    flash(msg, cat)
    if ok:
        invalidate_user_cache(user_id)
    return _back()


@bp.route("/currency_market/accept/<int:offer_id>", methods=["POST"])
@login_required
def accept_offer(offer_id):
    user_id = session["user_id"]
    with get_request_cursor() as db:
        ok, msg, cat = services.accept_offer(db, user_id, offer_id, request.form.get("amount"))
    flash(msg, cat)
    if ok:
        invalidate_user_cache(user_id)
    return _back()
