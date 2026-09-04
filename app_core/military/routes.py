from flask import Blueprint, request, render_template, session, redirect
from helpers import login_required, error, is_theme_v2_enabled
from database import get_request_cursor, cache_response, invalidate_user_cache, invalidate_view_cache
from variables import MILDICT
from app_core.upgrades.services import get_upgrades

from .repositories import ALL_UNITS, STOCKPILE_UNITS, get_user_units_with_stats, get_manpower_and_gold, get_user_stockpile
from .services import compute_display_limits, process_sell_units, process_buy_units, process_activate_units

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
            stockpile = get_user_stockpile(db, cId)
            limits = compute_display_limits(cId, db, units_dict, stockpile)
            upgrades = get_upgrades(cId, db=db)  # Reuse cursor

        template = "military_v2.html" if is_theme_v2_enabled("military") else "military.html"
        return render_template(
            template,
            units=units_dict,
            units_active=units_active,
            limits=limits,
            upgrades=upgrades,
            mildict=MILDICT,
            manpower=manpower,
            stockpile=stockpile,
        )

@bp.route("/military/<way>/<units>", methods=["POST"])
@login_required
def military_sell_buy(way, units):
    if request.method == "POST":
        cId = session["user_id"]

        with get_request_cursor() as db:
            if units not in ALL_UNITS:
                return error(400, "No such unit exists.")

            if units in STOCKPILE_UNITS:
                return error(400, "This unit is activated from its stockpile — see /military/activate.")

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

        try:
            invalidate_user_cache(cId)
            invalidate_view_cache("military", user_id=cId)
        except Exception:
            pass

        return redirect("/military")

@bp.route("/military/activate/<units>", methods=["POST"])
@login_required
def military_activate(units):
    cId = session["user_id"]

    if units not in STOCKPILE_UNITS:
        return error(400, "No such stockpile unit exists.")

    units_str = request.form.get(units)
    if not units_str:
        return error(400, "Unit amount is required")

    try:
        wantedUnits = int(units_str)
    except (ValueError, TypeError):
        return error(400, "Unit amount must be a valid number")

    if wantedUnits < 1:
        return error(400, "You cannot activate less than 1 unit")

    with get_request_cursor() as db:
        success, msg = process_activate_units(db, cId, units, wantedUnits, MILDICT)
        if not success:
            return error(400, msg)

    try:
        invalidate_user_cache(cId)
        invalidate_view_cache("military", user_id=cId)
    except Exception:
        pass

    return redirect("/military")
