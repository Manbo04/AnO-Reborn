from flask import Blueprint, request, render_template, session, redirect, flash

from helpers import login_required, require_post_origin
from database import get_request_cursor, invalidate_view_cache

from .services import (
    get_role,
    get_coalition_name,
    propose_trade,
    accept_trade,
    decline_trade,
    get_trades_page,
    set_insured,
    get_insurance_page,
)

bp = Blueprint("coalition_bank", __name__)


def _invalidate(coalition_id):
    # Same 30s view caches the coalition bank's own deposit/withdraw clear.
    if coalition_id:
        invalidate_view_cache("coalition", page=f"/coalition/{coalition_id}")
    invalidate_view_cache("my_coalition")


def _trades_url(coalition_id):
    return f"/coalition/{coalition_id}/bank-trades"


@bp.route("/coalition/<int:coalition_id>/bank-trades", methods=["GET"])
@login_required
def bank_trades(coalition_id):
    user_id = session.get("user_id")
    with get_request_cursor() as db:
        if not get_role(db, user_id, coalition_id):
            flash("You're not in that coalition.", "warning")
            return redirect("/my_coalition")
        page = get_trades_page(db, user_id, coalition_id)
        col_name = get_coalition_name(db, coalition_id)
    return render_template(
        "coalition_bank_trades.html", page=page, coalition_id=coalition_id, col_name=col_name
    )


@bp.route("/coalition/<int:coalition_id>/bank-trades/propose", methods=["POST"])
@login_required
@require_post_origin
def propose_bank_trade(coalition_id):
    user_id = session.get("user_id")
    with get_request_cursor() as db:
        ok, message = propose_trade(
            db,
            user_id,
            coalition_id,
            request.form.get("give_resource"),
            request.form.get("give_amount"),
            request.form.get("want_resource"),
            request.form.get("want_amount"),
            request.form.get("note"),
        )
        if not ok:
            db.connection.rollback()
    flash(message, "success" if ok else "danger")
    return redirect(_trades_url(coalition_id))


def _resolve(trade_id, action):
    user_id = session.get("user_id")
    with get_request_cursor() as db:
        if action == "accept":
            ok, message, coalition_id = accept_trade(db, user_id, trade_id)
        else:
            ok, message, coalition_id = decline_trade(db, user_id, trade_id, cancel=(action == "cancel"))
    if ok:
        _invalidate(coalition_id)
    flash(message, "success" if ok else "danger")
    return redirect(_trades_url(coalition_id) if coalition_id else "/my_coalition")


@bp.route("/coalition/bank-trades/<int:trade_id>/accept", methods=["POST"])
@login_required
@require_post_origin
def accept_bank_trade(trade_id):
    return _resolve(trade_id, "accept")


@bp.route("/coalition/bank-trades/<int:trade_id>/decline", methods=["POST"])
@login_required
@require_post_origin
def decline_bank_trade(trade_id):
    return _resolve(trade_id, "decline")


@bp.route("/coalition/bank-trades/<int:trade_id>/cancel", methods=["POST"])
@login_required
@require_post_origin
def cancel_bank_trade(trade_id):
    return _resolve(trade_id, "cancel")


@bp.route("/coalition/<int:coalition_id>/bond-insurance", methods=["GET"])
@login_required
def bond_insurance(coalition_id):
    user_id = session.get("user_id")
    with get_request_cursor() as db:
        if not get_role(db, user_id, coalition_id):
            flash("You're not in that coalition.", "warning")
            return redirect("/my_coalition")
        page = get_insurance_page(db, user_id, coalition_id)
        col_name = get_coalition_name(db, coalition_id)
    return render_template(
        "coalition_bond_insurance.html", page=page, coalition_id=coalition_id, col_name=col_name
    )


@bp.route("/coalition/<int:coalition_id>/bond-insurance/set", methods=["POST"])
@login_required
@require_post_origin
def set_bond_insurance(coalition_id):
    user_id = session.get("user_id")
    try:
        member_id = int(request.form.get("member_id", ""))
    except ValueError:
        flash("Pick a member.", "danger")
        return redirect(f"/coalition/{coalition_id}/bond-insurance")
    insured = request.form.get("insured") == "1"
    with get_request_cursor() as db:
        ok, message = set_insured(db, user_id, coalition_id, member_id, insured)
    flash(message, "success" if ok else "danger")
    return redirect(f"/coalition/{coalition_id}/bond-insurance")
