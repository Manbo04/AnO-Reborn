from flask import Blueprint, request, render_template, session, redirect, flash, url_for

from helpers import login_required
from database import get_request_cursor

from .services import get_loan_status, take_loan, repay_loan, fetch_loan_history

bp = Blueprint("loans", __name__)


@bp.route("/loans", methods=["GET"])
@login_required
def view_loans():
    user_id = session.get("user_id")
    with get_request_cursor() as db:
        status = get_loan_status(db, user_id)
        history = fetch_loan_history(db, user_id)

    # New page, built after the sitewide v2 migration completed (all 15
    # pre-existing pages) -- no classic template exists or is needed, unlike
    # is_theme_v2_enabled()-gated pages that predate the redesign.
    return render_template("loans_v2.html", status=status, history=history)


@bp.route("/loans/take", methods=["POST"])
@login_required
def take_loan_route():
    user_id = session.get("user_id")
    amount = request.form.get("amount")

    with get_request_cursor() as db:
        ok, error, category = take_loan(db, user_id, amount)

    if not ok:
        flash(error, category)
        return redirect(url_for("loans.view_loans"))

    flash("Loan approved — gold has been added to your treasury.", "success")
    return redirect(url_for("loans.view_loans"))


@bp.route("/loans/repay", methods=["POST"])
@login_required
def repay_loan_route():
    user_id = session.get("user_id")
    amount = request.form.get("amount")

    with get_request_cursor() as db:
        ok, error, category = repay_loan(db, user_id, amount)

    if not ok:
        flash(error, category)
        return redirect(url_for("loans.view_loans"))

    flash("Repayment applied.", "success")
    return redirect(url_for("loans.view_loans"))
