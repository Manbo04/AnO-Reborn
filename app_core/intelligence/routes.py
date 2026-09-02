from flask import Blueprint, request, render_template, session, redirect
from psycopg2.extras import RealDictCursor

from helpers import login_required, error, is_theme_v2_enabled
from database import get_request_cursor, cache_response, invalidate_view_cache

from .repositories import get_username
from .services import (
    fetch_spy_reports,
    sort_spy_reports,
    get_spy_amount_form_data,
    submit_spy_amount,
    resolve_spy_operation,
)

bp = Blueprint("intelligence", __name__)


# TODO: add complex operation sorting by date and merging
@bp.route("/intelligence", methods=["GET"])
@login_required
@cache_response(ttl_seconds=30)  # Cache spy info for 30 seconds
def intelligence():
    cId = session["user_id"]
    template = "intelligence_v2.html" if is_theme_v2_enabled("intelligence") else "intelligence.html"

    try:
        with get_request_cursor(cursor_factory=RealDictCursor) as db:
            data = fetch_spy_reports(db, cId)
    except Exception:
        # If anything unexpected happens reading spyinfo, return an empty page
        return render_template(template, info={})

    info = sort_spy_reports(data)
    return render_template(template, info=info)


@bp.route("/spyAmount", methods=["GET", "POST"])
@login_required
def spyAmount():
    cId = session["user_id"]
    if request.method == "GET":
        with get_request_cursor() as db:
            yourCountry, spies = get_spy_amount_form_data(db, cId)

        return render_template("spyAmount.html", yourCountry=yourCountry, spies=spies)

    # make the spy entry here
    if request.method == "POST":
        try:
            int(request.form.get("prep", 1) or 1)
            spies = int(request.form.get("amount", 1) or 1)
            eId = int(request.form.get("enemy", 0))
        except (ValueError, TypeError):
            return error(400, "Invalid input values.")

        if eId < 1:
            return error(400, "Invalid target.")

        with get_request_cursor() as db:
            submit_spy_amount(db, cId, eId)

        # Removed spoofing and leaking functionality
        return redirect("/intelligence")


# TODO: add notifications
@bp.route("/spyResult", methods=["GET", "POST"])
@login_required
def spyResult():
    if request.method == "GET":
        spyEntry = session.get("spyEntry", {})
        eId = session.get("eId")
        enemyNation = None
        if eId:
            with get_request_cursor() as db:
                enemyNation = get_username(db, eId)

        return render_template(
            "spyResult.html", enemyNation=enemyNation, spyEntry=spyEntry
        )
    if request.method == "POST":
        cId = session["user_id"]
        eId = request.form.get("country")

        spies_str = request.form.get("spies")
        if not spies_str:
            return error(400, "Number of spies is required")

        try:
            spies = int(spies_str)
        except (ValueError, TypeError):
            return error(400, "Number of spies must be a valid number")

        spy_type = request.form.get("spy_type")

        with get_request_cursor() as db:
            ok, status_code, message = resolve_spy_operation(db, cId, eId, spies, spy_type)

        if not ok:
            return error(status_code, message)

        try:
            invalidate_view_cache("intelligence", user_id=cId)
        except Exception:
            pass

        return redirect("/intelligence")
