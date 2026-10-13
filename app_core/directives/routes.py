from flask import Blueprint, flash, redirect, render_template, session

from database import get_request_cursor
from helpers import login_required

from .services import activate, list_for_user

bp = Blueprint("directives", __name__)


def _hourly_income(user_id):
    from app_core.game_ticks.taxes import calc_ti

    income, _ = calc_ti(user_id)
    return int(income or 0)


@bp.route("/directives", methods=["GET"])
@login_required
def view_directives():
    user_id = session["user_id"]
    income = _hourly_income(user_id)
    with get_request_cursor(read_only=True) as db:
        rows = list_for_user(db, user_id, income)
    return render_template("directives.html", directives=rows)


@bp.route("/directives/activate/<key>", methods=["POST"])
@login_required
def activate_directive(key):
    user_id = session["user_id"]
    income = _hourly_income(user_id)
    with get_request_cursor() as db:
        ok, message = activate(db, user_id, key, income)
    flash(message, "success" if ok else "danger")
    return redirect("/directives")
