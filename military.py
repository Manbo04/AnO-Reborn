from flask import Blueprint, request, render_template, session, redirect
from helpers import login_required, error
from database import get_db_cursor, cache_response
from dotenv import load_dotenv
from helpers import get_date
from upgrades import get_upgrades
from variables import MILDICT

load_dotenv()

bp = Blueprint("military", __name__)

ALL_UNITS = [
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
]


def _get_user_units_with_stats(db, cId):
    """Get user units with combat stats and maintenance costs."""
    db.execute(
        """
        SELECT
            ud.name,
            COALESCE(um.quantity, 0) AS quantity,
            ud.base_attack,
            ud.base_defense,
            rd.name AS maintenance_resource,
            ud.maintenance_cost_amount
        FROM unit_dictionary ud
        LEFT JOIN user_military um
            ON um.unit_id = ud.unit_id AND um.user_id = %s
        LEFT JOIN resource_dictionary rd
            ON rd.resource_id = ud.maintenance_cost_resource_id
        WHERE ud.is_active = TRUE
        ORDER BY ud.name
        """,
        (cId,),
    )
    units_list = []
    units_dict = {}
    for row in db.fetchall():
        name, qty, attack, defense, maint_resource, maint_amount = row
        qty = int(qty or 0)
        attack = float(attack or 0)
        defense = float(defense or 0)
        maint_amount = int(maint_amount or 0)
        maint_cost_per_tick = qty * maint_amount

        unit_info = {
            "name": name,
            "quantity": qty,
            "attack": attack,
            "defense": defense,
            "maintenance_resource": maint_resource,
            "maintenance_per_unit": maint_amount,
            "maintenance_per_tick": maint_cost_per_tick,
        }
        units_dict[name] = unit_info
        if qty > 0:
            units_list.append(unit_info)

    # Ensure all units exist in dict with 0 quantity
    for unit in ALL_UNITS:
        if unit not in units_dict:
            units_dict[unit] = {
                "name": unit,
                "quantity": 0,
                "attack": 0,
                "defense": 0,
                "maintenance_resource": None,
                "maintenance_per_unit": 0,
                "maintenance_per_tick": 0,
            }

    return units_dict, units_list


def _get_user_units(db, cId):
    """Get user units (legacy interface for compatibility)."""
    units_dict, _ = _get_user_units_with_stats(db, cId)
    return {name: info["quantity"] for name, info in units_dict.items()}


def _get_unit_costs(db, unit_name):
    db.execute(
        """
        SELECT
            unit_id,
            COALESCE(manpower_required, 0) AS manpower_required,
            COALESCE(production_cost_rations, 0) AS production_cost_rations,
            COALESCE(production_cost_components, 0) AS production_cost_components,
            COALESCE(production_cost_steel, 0) AS production_cost_steel,
            COALESCE(production_cost_fuel, 0) AS production_cost_fuel
        FROM unit_dictionary
        WHERE name=%s AND is_active=TRUE
        """,
        (unit_name,),
    )
    row = db.fetchone()
    if not row:
        return None

    (
        unit_id,
        manpower_required,
        cost_rations,
        cost_components,
        cost_steel,
        cost_fuel,
    ) = row
    costs = {
        "rations": int(cost_rations or 0),
        "components": int(cost_components or 0),
        "steel": int(cost_steel or 0),
        "gasoline": int(cost_fuel or 0),
    }
    costs = {k: v for k, v in costs.items() if v > 0}

    # Gold cost is currently sourced from MILDICT until dedicated DB column exists.
    gold_cost = int(MILDICT.get(unit_name, {}).get("price", 0) or 0)
    manpower_cost = int(
        manpower_required or MILDICT.get(unit_name, {}).get("manpower", 0) or 0
    )

    return {
        "unit_id": int(unit_id),
        "gold_cost": gold_cost,
        "resource_costs": costs,
        "manpower_cost": manpower_cost,
    }


def _get_resource_balance(db, cId, resource):
    db.execute(
        """
        SELECT COALESCE(ue.quantity, 0)
        FROM resource_dictionary rd
        LEFT JOIN user_economy ue
            ON ue.resource_id = rd.resource_id AND ue.user_id = %s
        WHERE rd.name=%s AND rd.is_active=TRUE
        """,
        (cId, resource),
    )
    row = db.fetchone()
    return int(row[0] or 0) if row else 0


def _adjust_resource(db, cId, resource, delta):
    db.execute(
        """
        INSERT INTO user_economy (user_id, resource_id, quantity)
        SELECT %s, rd.resource_id, 0
        FROM resource_dictionary rd
        WHERE rd.name=%s AND rd.is_active=TRUE
        ON CONFLICT (user_id, resource_id) DO NOTHING
        """,
        (cId, resource),
    )
    db.execute(
        """
        UPDATE user_economy ue
        SET quantity = ue.quantity + %s
        FROM resource_dictionary rd
        WHERE ue.user_id=%s
          AND ue.resource_id = rd.resource_id
          AND rd.name=%s
          AND rd.is_active=TRUE
        """,
        (delta, cId, resource),
    )


def compute_display_limits(cId, units_row=None):
    """Return limits as shown on the military page (apaches limited by
    army_bases, fighters/bombers limited by aerodomes).

    - `units_row` may be passed (dict) to avoid an extra DB fetch when the
      caller already has current military counts.
    """
    with get_db_cursor() as db:
        db.execute(
            """
            SELECT
                COALESCE(
                    SUM(CASE WHEN bd.name='army_bases' THEN ub.quantity ELSE 0 END),
                    0
                ) AS army_bases,
                COALESCE(
                    SUM(CASE WHEN bd.name='harbours' THEN ub.quantity ELSE 0 END),
                    0
                ) AS harbours,
                COALESCE(
                    SUM(CASE WHEN bd.name='aerodomes' THEN ub.quantity ELSE 0 END),
                    0
                ) AS aerodomes,
                COALESCE(
                    SUM(
                        CASE WHEN bd.name='admin_buildings' THEN ub.quantity ELSE 0 END
                    ),
                    0
                ) AS admin_buildings,
                COALESCE(
                    SUM(CASE WHEN bd.name='silos' THEN ub.quantity ELSE 0 END),
                    0
                ) AS silos
            FROM user_buildings ub
            JOIN building_dictionary bd ON bd.building_id = ub.building_id
            JOIN provinces p ON p.id = ub.province_id
            WHERE p.userId=%s
            """,
            (cId,),
        )
        army_bases, harbours, aerodomes, admin_buildings, silos = db.fetchone()

    military = units_row or {}
    for unit in ALL_UNITS:
        military.setdefault(unit, 0)

    # Land units
    soldiers = max(0, army_bases * 100 - military["soldiers"])
    tanks = max(0, army_bases * 8 - military["tanks"])
    artillery = max(0, army_bases * 8 - military["artillery"])

    # Air units share aerodome capacity
    air_units = military["fighters"] + military["bombers"]
    air_limit = max(0, aerodomes * 5 - air_units)
    bombers = air_limit
    fighters = air_limit
    apaches = max(0, army_bases * 5 - military["apaches"])

    # Naval units
    naval_units = military["submarines"] + military["destroyers"]
    naval_limit = max(0, harbours * 3 - naval_units)
    submarines = naval_limit
    destroyers = naval_limit
    cruisers = max(0, harbours * 2 - military["cruisers"])

    # Specials
    spies = max(0, admin_buildings * 1 - military["spies"])
    icbms = max(0, silos + 1 - military["icbms"])
    nukes = max(0, silos - military["nukes"])

    upgrades = get_upgrades(cId)
    if upgrades.get("increasedfunding"):
        spies = int(spies * 1.4)

    return {
        "soldiers": soldiers,
        "tanks": tanks,
        "artillery": artillery,
        "bombers": bombers,
        "fighters": fighters,
        "apaches": apaches,
        "destroyers": destroyers,
        "cruisers": cruisers,
        "submarines": submarines,
        "spies": spies,
        "icbms": icbms,
        "nukes": nukes,
    }


@bp.route("/military", methods=["GET", "POST"])
@login_required
@cache_response(ttl_seconds=10)  # Short cache for military page
def military():
    cId = session["user_id"]

    if request.method == "GET":
        with get_db_cursor() as db:
            units_dict, units_active = _get_user_units_with_stats(db, cId)
            # Manpower was in the legacy `military` table which no longer exists.
            # Default to 0 until a migration adds it elsewhere.
            manpower = 0
            try:
                db.execute(
                    "SELECT COALESCE(manpower, 0) FROM military WHERE id=%s", (cId,)
                )
                manpower_row = db.fetchone()
                manpower = int(manpower_row[0] or 0) if manpower_row else 0
            except Exception:
                manpower = 0

        upgrades = get_upgrades(cId)  # Now cached in upgrades.py
        limits = compute_display_limits(cId, units_dict)

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
def military_sell_buy(way, units):  # WARNING: function used only for military
    if request.method == "POST":
        cId = session["user_id"]

        with get_db_cursor() as db:
            if units not in ALL_UNITS:
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

            unit_costs = _get_unit_costs(db, units)
            if not unit_costs:
                return error(400, "Unit definition not found or inactive")

            price = unit_costs["gold_cost"]
            resources = unit_costs["resource_costs"]
            manpower_per_unit = unit_costs["manpower_cost"]
            unit_id = unit_costs["unit_id"]

            # Existing unit amount
            db.execute(
                "SELECT COALESCE(quantity, 0) "
                "FROM user_military WHERE user_id=%s AND unit_id=%s",
                (cId, unit_id),
            )
            current_row = db.fetchone()
            currentUnits = int(current_row[0] or 0) if current_row else 0

            # Manpower was in the legacy `military` table. Try to read it;
            # fall back to 0 if the table no longer exists.
            manpower_available = 0
            try:
                db.execute(
                    "INSERT INTO military (id, manpower) VALUES (%s, 0) "
                    "ON CONFLICT (id) DO NOTHING",
                    (cId,),
                )
                db.execute(
                    "SELECT COALESCE(manpower, 0) FROM military WHERE id=%s", (cId,)
                )
                manpower_available = int(db.fetchone()[0] or 0)
            except Exception:
                manpower_available = 0

            db.execute("SELECT COALESCE(gold, 0) FROM stats WHERE id=%s", (cId,))
            gold = int(db.fetchone()[0] or 0)

            totalPrice = wantedUnits * price

            if way == "sell":
                if wantedUnits > currentUnits:
                    return error(400, f"Not enough {units} (have {currentUnits})")

                for resource, amount in resources.items():
                    addResources = wantedUnits * amount
                    _adjust_resource(db, cId, resource, addResources)

                db.execute(
                    "UPDATE user_military SET quantity = quantity - %s "
                    "WHERE user_id=%s AND unit_id=%s",
                    (wantedUnits, cId, unit_id),
                )
                db.execute(
                    "UPDATE stats SET gold=gold+%s WHERE id=%s",
                    (
                        totalPrice,
                        cId,
                    ),
                )
                # Manpower return on sell — silently skip if military table gone
                try:
                    db.execute(
                        "UPDATE military SET manpower=manpower+%s WHERE id=%s",
                        (wantedUnits * manpower_per_unit, cId),
                    )
                except Exception:
                    pass

                # flash(f"You sold {wantedUnits} {units}")
            elif way == "buy":
                # Use the same display limits logic as the military page so the
                # buy checks match what users see.
                units_map = _get_user_units(db, cId)
                limits = compute_display_limits(cId, units_map)

                if wantedUnits > limits[units]:
                    return error(
                        400,
                        f"Unit buy limit exceeded (allowed {limits[units]})",
                    )

                if (
                    totalPrice > gold
                ):  # checks if user wants to buy more units than he has gold
                    return error(400, f"Not enough money ({gold}/{totalPrice})")

                needed_manpower = wantedUnits * manpower_per_unit
                if needed_manpower > manpower_available:
                    return error(
                        400,
                        f"Not enough manpower ({manpower_available}/{needed_manpower})",
                    )

                for resource, amount in resources.items():
                    currentResources = _get_resource_balance(db, cId, resource)
                    requiredResources = amount * wantedUnits

                    if requiredResources > currentResources:
                        return error(
                            400,
                            f"{resource}: need {requiredResources-currentResources}",
                        )

                for resource, amount in resources.items():
                    requiredResources = amount * wantedUnits
                    _adjust_resource(db, cId, resource, -requiredResources)

                db.execute(
                    "UPDATE stats SET gold=gold-%s WHERE id=%s", (totalPrice, cId)
                )
                db.execute(
                    """
                    INSERT INTO user_military (user_id, unit_id, quantity)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id, unit_id)
                    DO UPDATE SET quantity = user_military.quantity + EXCLUDED.quantity
                    """,
                    (cId, unit_id, wantedUnits),
                )

                # Manpower deduct on buy — silently skip if military table gone
                try:
                    db.execute(
                        "UPDATE military SET manpower=manpower-%s WHERE id=%s",
                        (needed_manpower, cId),
                    )
                except Exception:
                    pass

            else:
                return error(404, "Page not found")

            # UPDATING REVENUE
            if way == "buy":
                rev_type = "expense"
            elif way == "sell":
                rev_type = "revenue"
            name = f"{way.capitalize()}ing {wantedUnits} {units} for your military."
            description = ""

            db.execute(
                (
                    "INSERT INTO revenue (user_id, type, name, description, "
                    "date, resource, amount) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                ),
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
