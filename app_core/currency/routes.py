from flask import Blueprint, request, session, redirect, flash, url_for

from helpers import login_required
from database import get_request_cursor

from .services import mint_currency, redeem_currency

bp = Blueprint("currency", __name__)


@bp.route("/currency/mint", methods=["POST"])
@login_required
def mint_currency_route():
    user_id = session.get("user_id")
    units = request.form.get("units")

    with get_request_cursor() as db:
        ok, error, category = mint_currency(db, user_id, units)

    if not ok:
        flash(error, category)
    else:
        flash("Currency minted from your treasury.", "success")
    return redirect(url_for("country", cId=user_id))


@bp.route("/currency/redeem", methods=["POST"])
@login_required
def redeem_currency_route():
    user_id = session.get("user_id")
    units = request.form.get("units")

    with get_request_cursor() as db:
        ok, error, category = redeem_currency(db, user_id, units)

    if not ok:
        flash(error, category)
    else:
        flash("Currency redeemed back into gold.", "success")
    return redirect(url_for("country", cId=user_id))
