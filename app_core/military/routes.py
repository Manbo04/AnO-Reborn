from flask import Blueprint, request, render_template, session, redirect
from helpers import login_required, error
from database import get_request_cursor, cache_response
from variables import MILDICT
from upgrades import get_upgrades

from .repositories import ALL_UNITS, get_user_units_with_stats, get_manpower_and_gold
from .services import compute_display_limits, process_sell_units, process_buy_units

bp = Blueprint("military", __name__)

@bp.route("/military", methods=["GET", "POST"])
@login_required
@cache_response(ttl_seconds=30)  # Cache military page
def military():
    cId = session["user_id"]

    if request.method == "GET":
        with get_request_cursor() as db:
            units_dict, units_active = get_user_units_with_stats(db, cId)
            manpower, _ = get_manpower_and_gold(db, cId)
            limits = compute_display_limits(cId, db, units_dict)
            upgrades = get_upgrades(cId, db=db)  # Reuse cursor

        return render_template(
            "military.html",
            units=units_dict,
            units_active=units_active,
            limits=limits,
            upgrades=upgrades,
            mildict=MILDICT,
            manpower=manpower,
        )

@bp.route("/military/<way>/<units>", methods=["POST"])
@login_required
def military_sell_buy(way, units):
    if request.method == "POST":
        cId = session["user_id"]

        with get_request_cursor() as db:
            if units not in ALL_UNITS:
                return error(400, "No such unit exists.")

            units_str = request.form.get(units)
            if not units_str:
                return error(400, "Unit amount is required")

            try:
                wantedUnits = int(units_str)
            except (ValueError, TypeError):
                return error(400, "Unit amount must be a valid number")

            if wantedUnits < 1:
                return error(400, "You cannot buy or sell less than 1 unit")

            if way == "sell":
                success, msg = process_sell_units(db, cId, units, wantedUnits, MILDICT)
                if not success:
                    return error(400, msg)
            elif way == "buy":
                success, msg = process_buy_units(db, cId, units, wantedUnits, MILDICT)
                if not success:
                    return error(400, msg)
            else:
                return error(404, "Page not found")

        return redirect("/military")
