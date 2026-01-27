from flask import Blueprint, request, render_template, session, redirect
from src.helpers import login_required, error
from src.database import get_db_cursor, cache_response
from attack_scripts import Military
from dotenv import load_dotenv
from src.helpers import get_date
from upgrades import get_upgrades
from variables import MILDICT

load_dotenv()

bp = Blueprint("military", __name__)


@bp.route("/military", methods=["GET", "POST"])
@login_required
@cache_response(ttl_seconds=10)  # Short cache for military page
def military():
    cId = session["user_id"]

    if request.method == "GET":
        # OPTIMIZED: get_military and get_special are already single queries
        # manpower is now fetched together with military units
        from psycopg2.extras import RealDictCursor

        with get_db_cursor(cursor_factory=RealDictCursor) as db:
            # Single query for all military data including manpower
            db.execute(
                """SELECT tanks, soldiers, artillery, bombers, fighters, apaches,
                   destroyers, cruisers, submarines, spies, ICBMs as icbms, nukes, manpower
                   FROM military WHERE id=%s""",
                (cId,),
            )
            mil_data = db.fetchone()
            if mil_data:
                mil_data = dict(mil_data)
                manpower = mil_data.pop("manpower", 0)
                units = mil_data
            else:
                units = {}
                manpower = 0

        upgrades = get_upgrades(cId)  # Now cached in upgrades.py
        limits = Military.get_limits(cId)

        return render_template(
            "military.html",
            units=units,
            limits=limits,
            upgrades=upgrades,
            mildict=MILDICT,
            manpower=manpower,
        )


@bp.route("/military/<way>/<units>", methods=["POST"])
@login_required
def military_sell_buy(way, units):  # WARNING: function used only for military
    if request.method == "POST":
        cId = session["user_id"]

        with get_db_cursor() as db:
            allUnits = [
                "soldiers",
                "tanks",
                "artillery",
                "bombers",
                "fighters",
                "apaches",
                "destroyers",
                "cruisers",
                "submarines",
                "spies",
                "icbms",
                "nukes",
            ]  # list of allowed units

            if units not in allUnits and units != "apaches":
                return error("No such unit exists.", 400)

            units_str = request.form.get(units)
            if not units_str:
                return error(400, "Unit amount is required")

            try:
                wantedUnits = int(units_str)
            except (ValueError, TypeError):
                return error(400, "Unit amount must be a valid number")

            if wantedUnits < 1:
                return error(400, "You cannot buy or sell less than 1 unit")

            if units == "soldiers":
                db.execute(
                    "SELECT widespreadpropaganda FROM upgrades WHERE user_id=%s", (cId,)
                )
                wp = db.fetchone()[0]
                if wp:
                    MILDICT["soldiers"]["price"] *= 0.65

            # TODO: clear this mess i called code once i get the time
            # if you're reading this please excuse the messiness

            price = MILDICT[units]["price"]

            db.execute("SELECT gold FROM stats WHERE id=%s", (cId,))
            gold = db.fetchone()[0]

            totalPrice = wantedUnits * price

            curUnStat = f"SELECT {units} FROM military " + "WHERE id=%s"
            db.execute(curUnStat, (cId,))
            currentUnits = db.fetchone()[0]

            resources = MILDICT[units]["resources"]

            if way == "sell":
                if wantedUnits > currentUnits:
                    return error(
                        400,
                        f"You don't have enough {units} to sell ({wantedUnits}/{currentUnits})",
                    )

                for resource, amount in resources.items():
                    addResources = wantedUnits * amount
                    updateResource = (
                        f"UPDATE resources SET {resource}={resource}"
                        + "+%s WHERE id=%s"
                    )
                    db.execute(
                        updateResource,
                        (
                            addResources,
                            cId,
                        ),
                    )

                unitUpd = f"UPDATE military SET {units}={units}" + "-%s WHERE id=%s"
                db.execute(
                    unitUpd,
                    (
                        wantedUnits,
                        cId,
                    ),
                )
                db.execute(
                    "UPDATE stats SET gold=gold+%s WHERE id=%s",
                    (
                        totalPrice,
                        cId,
                    ),
                )
                db.execute(
                    "UPDATE military SET manpower=manpower+%s WHERE id=%s",
                    (wantedUnits * MILDICT[units]["manpower"], cId),
                )

                # flash(f"You sold {wantedUnits} {units}")
            elif way == "buy":
                limits = Military.get_limits(cId)

                if wantedUnits > limits[units]:
                    return error(
                        400,
                        f"You exceeded the unit buy limit, you might want to buy more military buildings. You can buy {limits[units]}/{wantedUnits} {units}.",
                    )

                if (
                    totalPrice > gold
                ):  # checks if user wants to buy more units than he has gold
                    return error(
                        400,
                        f"You don't have enough money for that ({gold}/{totalPrice}). You need {totalPrice-gold} more money.",
                    )

                # OPTIMIZATION: Batch fetch all required resources in ONE query
                resource_names = list(resources.keys())
                resource_cols = ", ".join(resource_names)
                db.execute(f"SELECT {resource_cols} FROM resources WHERE id=%s", (cId,))
                current_resources_row = db.fetchone()
                current_resources = (
                    dict(zip(resource_names, current_resources_row))
                    if current_resources_row
                    else {}
                )

                for resource, amount in resources.items():
                    currentResources = current_resources.get(resource, 0) or 0
                    requiredResources = amount * wantedUnits

                    if requiredResources > currentResources:
                        return error(
                            400,
                            f"You have {currentResources}/{requiredResources} {resource}, meaning you need {requiredResources-currentResources} more.",
                        )

                for resource, amount in resources.items():
                    requiredResources = amount * wantedUnits
                    updateResource = (
                        f"UPDATE resources SET {resource}={resource}"
                        + "-%s WHERE id=%s"
                    )
                    db.execute(updateResource, (requiredResources, cId))

                db.execute(
                    "UPDATE stats SET gold=gold-%s WHERE id=%s", (totalPrice, cId)
                )
                updMil = f"UPDATE military SET {units}={units}" + "+%s WHERE id=%s"
                db.execute(updMil, (wantedUnits, cId))

                db.execute(
                    "UPDATE military SET manpower=manpower-%s WHERE id=%s",
                    (wantedUnits * MILDICT[units]["manpower"], cId),
                )

            else:
                return error(404, "Page not found")

            ####### UPDATING REVENUE #############
            if way == "buy":
                rev_type = "expense"
            elif way == "sell":
                rev_type = "revenue"
            name = f"{way.capitalize()}ing {wantedUnits} {units} for your military."
            description = ""

            db.execute(
                "INSERT INTO revenue (user_id, type, name, description, date, resource, amount) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    cId,
                    rev_type,
                    name,
                    description,
                    get_date(),
                    units,
                    wantedUnits,
                ),
            )
            #######################################

        return redirect("/military")
