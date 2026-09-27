from flask import Blueprint, request, render_template, session, redirect, flash, url_for

from helpers import login_required
from database import get_request_cursor, invalidate_user_cache

from . import services

bp = Blueprint("currency_unions", __name__)


def _back(result):
    ok, message, category = result
    flash(message, category)
    return redirect(url_for("currency_unions.view_unions"))


@bp.route("/currency_unions", methods=["GET"])
@login_required
def view_unions():
    user_id = session.get("user_id")
    with get_request_cursor() as db:
        status = services.get_page_status(db, user_id)
    return render_template("currency_unions_v2.html", status=status)


@bp.route("/currency_unions/create", methods=["POST"])
@login_required
def create_union_route():
    user_id = session.get("user_id")
    with get_request_cursor() as db:
        result = services.create_union(
            db, user_id, request.form.get("name"), request.form.get("currency_name")
        )
    return _back(result)


@bp.route("/currency_unions/<int:union_id>/apply", methods=["POST"])
@login_required
def apply_route(union_id):
    user_id = session.get("user_id")
    with get_request_cursor() as db:
        result = services.apply_to_union(db, user_id, union_id)
    return _back(result)


@bp.route("/currency_unions/<int:union_id>/withdraw", methods=["POST"])
@login_required
def withdraw_route(union_id):
    user_id = session.get("user_id")
    with get_request_cursor() as db:
        result = services.withdraw_application(db, user_id, union_id)
    return _back(result)


@bp.route(
    "/currency_unions/<int:union_id>/applications/<int:applicant_id>/<decision>",
    methods=["POST"],
)
@login_required
def decide_route(union_id, applicant_id, decision):
    if decision not in ("approve", "decline"):
        flash("Unknown action.", "danger")
        return redirect(url_for("currency_unions.view_unions"))
    user_id = session.get("user_id")
    with get_request_cursor() as db:
        result = services.decide_application(
            db, user_id, union_id, applicant_id, decision == "approve"
        )
    invalidate_user_cache(applicant_id)
    return _back(result)


@bp.route("/currency_unions/leave", methods=["POST"])
@login_required
def leave_route():
    user_id = session.get("user_id")
    with get_request_cursor() as db:
        result = services.leave_union(db, user_id)
    invalidate_user_cache(user_id)
    return _back(result)


@bp.route("/currency_unions/<int:union_id>/kick/<int:member_id>", methods=["POST"])
@login_required
def kick_route(union_id, member_id):
    user_id = session.get("user_id")
    with get_request_cursor() as db:
        result = services.kick_member(db, user_id, union_id, member_id)
    invalidate_user_cache(member_id)
    return _back(result)
