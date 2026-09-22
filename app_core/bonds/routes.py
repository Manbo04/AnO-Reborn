from flask import Blueprint, request, render_template, session, redirect, flash, url_for

from helpers import login_required
from database import get_request_cursor, invalidate_user_cache

from .services import (
    get_market_status,
    create_bond,
    edit_bond,
    cancel_bond,
    fund_bond,
)

bp = Blueprint("bonds", __name__)


@bp.route("/bonds", methods=["GET"])
@login_required
def view_bonds():
    user_id = session.get("user_id")
    with get_request_cursor() as db:
        status = get_market_status(db, user_id)

    return render_template("bonds_v2.html", status=status)


@bp.route("/bonds/create", methods=["POST"])
@login_required
def create_bond_route():
    user_id = session.get("user_id")
    principal = request.form.get("principal")
    daily_interest_rate = request.form.get("daily_interest_rate")
    term_days = request.form.get("term_days")
    auto_escrow = request.form.get("auto_escrow") == "on"

    # The form collects a whole percent (e.g. "1.5" meaning 1.5%/day); the
    # service layer/DB store a fraction.
    try:
        daily_interest_rate = float(daily_interest_rate) / 100
    except (TypeError, ValueError):
        daily_interest_rate = None

    with get_request_cursor() as db:
        ok, error, category = create_bond(
            db, user_id, principal, daily_interest_rate, term_days, auto_escrow
        )

    if not ok:
        flash(error, category)
        return redirect(url_for("bonds.view_bonds"))

    flash("Bond listed on the market.", "success")
    return redirect(url_for("bonds.view_bonds"))


@bp.route("/bonds/<int:bond_id>/edit", methods=["POST"])
@login_required
def edit_bond_route(bond_id):
    user_id = session.get("user_id")
    principal = request.form.get("principal")
    daily_interest_rate = request.form.get("daily_interest_rate")
    term_days = request.form.get("term_days")
    auto_escrow = request.form.get("auto_escrow") == "on"

    try:
        daily_interest_rate = float(daily_interest_rate) / 100
    except (TypeError, ValueError):
        daily_interest_rate = None

    with get_request_cursor() as db:
        ok, error, category = edit_bond(
            db, bond_id, user_id, principal, daily_interest_rate, term_days, auto_escrow
        )

    flash(error if not ok else "Bond terms updated.", category if not ok else "success")
    return redirect(url_for("bonds.view_bonds"))


@bp.route("/bonds/<int:bond_id>/cancel", methods=["POST"])
@login_required
def cancel_bond_route(bond_id):
    user_id = session.get("user_id")
    with get_request_cursor() as db:
        ok, error, category = cancel_bond(db, bond_id, user_id)

    flash(error if not ok else "Bond listing cancelled.", category if not ok else "success")
    return redirect(url_for("bonds.view_bonds"))


@bp.route("/bonds/<int:bond_id>/fund", methods=["POST"])
@login_required
def fund_bond_route(bond_id):
    user_id = session.get("user_id")
    with get_request_cursor() as db:
        bond = None
        ok, error, category = fund_bond(db, bond_id, user_id)
        if ok:
            from .services import fetch_bond_detail
            bond = fetch_bond_detail(db, bond_id)

    if not ok:
        flash(error, category)
        return redirect(url_for("bonds.view_bonds"))

    try:
        invalidate_user_cache(user_id)
        if bond:
            invalidate_user_cache(bond[1])  # issuer_id
    except Exception:
        pass

    flash("Investment placed — principal transferred, daily interest starts accruing to you.", "success")
    return redirect(url_for("bonds.view_bonds"))
