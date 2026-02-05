from flask import Blueprint, request, render_template, session, redirect
from helpers import login_required, error
from dotenv import load_dotenv
import variables
from helpers import get_date
from database import get_db_cursor, cache_response, invalidate_user_cache
import os
import math

bp = Blueprint("province", __name__)

load_dotenv()


@bp.route("/provinces", methods=["GET"])
@login_required
@cache_response(ttl_seconds=30)
def provinces():
    with get_db_cursor() as db:
        cId = session["user_id"]

        db.execute(
            (
                "SELECT CAST(cityCount AS INTEGER) as cityCount, population, "
                "provinceName, id, land, happiness, "
                "productivity, energy FROM provinces WHERE userId=(%s) ORDER BY id ASC"
            ),
            (cId,),
        )
        provinces = db.fetchall()

        return render_template("provinces.html", provinces=provinces)


@bp.route("/province/<pId>", methods=["GET"])
@login_required
@cache_response(ttl_seconds=15)  # Short cache for province page (updates frequently)
def province(pId):
    from psycopg2.extras import RealDictCursor
    from database import get_db_connection, query_cache

    cId = session["user_id"]

    # OPTIMIZED: Single query to fetch province + infra + resources + stats
    # + upgrades - all in ONE database connection
    with get_db_connection() as conn:
        db = conn.cursor(cursor_factory=RealDictCursor)

        # Combined query - reduces 7+ queries to 1
        # Now also includes upgrades to avoid second connection
        db.execute(
            """
            SELECT p.id, p.userId AS user, p.provinceName AS name, p.population,
                   p.pollution, p.happiness, p.productivity, p.consumer_spending,
                   CAST(p.citycount AS INTEGER) as citycount,
                   p.land, p.energy AS electricity,
                   s.location, r.consumer_goods, r.rations, pi.*
            FROM provinces p
            LEFT JOIN stats s ON p.userId = s.id
            LEFT JOIN resources r ON p.userId = r.id
            LEFT JOIN proInfra pi ON p.id = pi.id
            WHERE p.id = %s
            """,
            (pId,),
        )
        result = db.fetchone()

        if not result:
            return error(404, "Province doesn't exist")

        # Convert to dict for template
        result = dict(result)

        # Get upgrades in the SAME connection (avoid opening new connection)
        user_id = result["user"]
        cache_key = f"upgrades_{user_id}"
        upgrades = query_cache.get(cache_key)
        if upgrades is None:
            db.execute("SELECT * FROM upgrades WHERE user_id=%s", (user_id,))
            upg_row = db.fetchone()
            upgrades = dict(upg_row) if upg_row else {}
            query_cache.set(cache_key, upgrades)

        # Build province dict from result
        province = {
            "id": result["id"],
            "user": result["user"],
            "name": result["name"],
            "population": result["population"],
            "pollution": result["pollution"],
            "happiness": result["happiness"],
            "productivity": result["productivity"],
            "consumer_spending": result["consumer_spending"],
            "citycount": result["citycount"],
            "land": result["land"],
            "electricity": result["electricity"],
            "location": result["location"]
            or "Grassland",  # Default to Grassland if NULL
        }

        # Build units dict from proInfra columns
        proinfra_columns = [
            "id",
            "coal_burners",
            "oil_burners",
            "solar_fields",
            "hydro_dams",
            "nuclear_reactors",
            "gas_stations",
            "general_stores",
            "farmers_markets",
            "malls",
            "banks",
            "city_parks",
            "hospitals",
            "libraries",
            "universities",
            "monorails",
            "army_bases",
            "aerodomes",
            "harbours",
            "admin_buildings",
            "silos",
            "farms",
            "pumpjacks",
            "coal_mines",
            "bauxite_mines",
            "copper_mines",
            "uranium_mines",
            "lead_mines",
            "iron_mines",
            "lumber_mills",
            "component_factories",
            "steel_mills",
            "ammunition_factories",
            "aluminium_refineries",
            "oil_refineries",
        ]
        # Handle None values from LEFT JOIN when proInfra is missing
        units = {col: (result.get(col) or 0) for col in proinfra_columns}

        # Calculate free slots in-memory (no extra queries)
        city_buildings = [
            "coal_burners",
            "oil_burners",
            "hydro_dams",
            "nuclear_reactors",
            "solar_fields",
            "gas_stations",
            "general_stores",
            "farmers_markets",
            "malls",
            "banks",
            "city_parks",
            "hospitals",
            "libraries",
            "universities",
            "monorails",
        ]
        land_buildings = [
            "army_bases",
            "harbours",
            "aerodomes",
            "admin_buildings",
            "silos",
            "farms",
            "pumpjacks",
            "coal_mines",
            "bauxite_mines",
            "copper_mines",
            "uranium_mines",
            "lead_mines",
            "iron_mines",
            "lumber_mills",
            "component_factories",
            "steel_mills",
            "ammunition_factories",
            "aluminium_refineries",
            "oil_refineries",
        ]

        used_city_slots = sum(units.get(b, 0) or 0 for b in city_buildings)
        used_land_slots = sum(units.get(b, 0) or 0 for b in land_buildings)

        province["free_cityCount"] = province["citycount"] - used_city_slots
        province["free_land"] = province["land"] - used_land_slots
        province["own"] = province["user"] == cId

        # Check consumer goods and rations from already-fetched data
        consumer_goods = result.get("consumer_goods", 0) or 0
        rations = result.get("rations", 0) or 0

        max_cg = math.ceil(province["population"] / variables.CONSUMER_GOODS_PER)
        enough_consumer_goods = consumer_goods >= max_cg

        rations_minus = province["population"] // variables.RATIONS_PER
        enough_rations = rations - rations_minus > 1

        # Calculate energy in-memory from proInfra data
        consumers = variables.ENERGY_CONSUMERS
        producers = variables.ENERGY_UNITS
        new_infra = variables.NEW_INFRA

        energy_consumption = sum(units.get(c, 0) or 0 for c in consumers)
        energy_production = sum(
            (units.get(p, 0) or 0) * new_infra[p]["plus"]["energy"] for p in producers
        )
        energy = {"consumption": energy_consumption, "production": energy_production}
        has_power = energy_production >= energy_consumption

        # upgrades already fetched in same connection above

        infra = variables.INFRA
        prices = variables.PROVINCE_UNIT_PRICES

        return render_template(
            "province.html",
            province=province,
            units=units,
            enough_consumer_goods=enough_consumer_goods,
            enough_rations=enough_rations,
            has_power=has_power,
            energy=energy,
            infra=infra,
            upgrades=upgrades,
            prices=prices,
            new_infra=new_infra,
        )


def get_province_price(user_id):
    with get_db_cursor() as db:
        db.execute("SELECT COUNT(id) FROM provinces WHERE userId=(%s)", (user_id,))
        current_province_amount = db.fetchone()[0]

        multiplier = 1 + (0.16 * current_province_amount)
        price = int(8000000 * multiplier)

        return price


@bp.route("/createprovince", methods=["GET", "POST"])
@login_required
def createprovince():
    cId = session["user_id"]

    if request.method == "POST":
        from database import get_db_connection

        with get_db_connection() as conn:
            db = conn.cursor()
            pName = request.form.get("name")

            # Acquire advisory lock to prevent double-submit race condition
            # Lock key is based on user ID to prevent same user creating multiple
            # provinces simultaneously
            lock_key = 100000 + cId  # Offset to avoid collision with other locks
            db.execute("SELECT pg_try_advisory_lock(%s)", (lock_key,))
            lock_result = db.fetchone()
            if not lock_result or not lock_result[0]:
                return error(400, "Province creation already in progress, please wait")

            try:
                # Use atomic gold deduction to prevent race conditions
                province_price = get_province_price(cId)

                db.execute(
                    "UPDATE stats SET gold = gold - %s "
                    "WHERE id = %s AND gold >= %s RETURNING gold",
                    (province_price, cId, province_price),
                )
                result = db.fetchone()
                if not result:
                    return error(400, "You don't have enough money.")

                db.execute(
                    (
                        "INSERT INTO provinces (userId, provinceName) "
                        "VALUES (%s, %s) RETURNING id"
                    ),
                    (cId, pName),
                )
                province_id = db.fetchone()[0]

                db.execute("INSERT INTO proInfra (id) VALUES (%s)", (province_id,))

                # Commit the transaction
                conn.commit()

                # Invalidate cached provinces page for this user
                # so the new province appears immediately
                try:
                    from database import query_cache

                    pattern = f"provinces_{cId}_"
                    query_cache.invalidate(pattern=pattern)
                except Exception:
                    # Best-effort: cache invalidation should not raise on failure
                    pass
            finally:
                # Always release the advisory lock
                try:
                    db.execute("SELECT pg_advisory_unlock(%s)", (lock_key,))
                except Exception:
                    pass

        return redirect("/provinces")
    else:
        price = get_province_price(cId)
        return render_template("createprovince.html", price=price)


def get_free_slots(pId, slot_type):  # pId = province id
    with get_db_cursor() as db:
        if slot_type == "city":
            db.execute(
                """
            SELECT
            coal_burners + oil_burners + hydro_dams + nuclear_reactors + solar_fields +
            gas_stations + general_stores + farmers_markets + malls + banks +
            city_parks + hospitals + libraries + universities + monorails
            FROM proInfra WHERE id=%s
            """,
                (pId,),
            )
            used_slots = int(db.fetchone()[0])

            db.execute("SELECT cityCount FROM provinces WHERE id=%s", (pId,))
            all_slots = int(db.fetchone()[0])

            free_slots = all_slots - used_slots

        elif slot_type == "land":
            db.execute(
                """
            SELECT
            army_bases + harbours + aerodomes + admin_buildings + silos +
            farms + pumpjacks + coal_mines + bauxite_mines +
            copper_mines + uranium_mines + lead_mines + iron_mines +
            lumber_mills + component_factories + steel_mills + ammunition_factories +
            aluminium_refineries + oil_refineries FROM proInfra WHERE id=%s
            """,
                (pId,),
            )
            used_slots = int(db.fetchone()[0])

            db.execute("SELECT land FROM provinces WHERE id=%s", (pId,))
            all_slots = int(db.fetchone()[0])

            free_slots = all_slots - used_slots

        return free_slots


@bp.route("/<way>/<units>/<province_id>", methods=["POST"])
@login_required
def province_sell_buy(way, units, province_id):
    cId = session["user_id"]

    with get_db_cursor() as db:
        import logging

        try:
            db.execute(
                "SELECT id FROM provinces WHERE id=%s AND userId=%s",
                (
                    province_id,
                    cId,
                ),
            )
            row = db.fetchone()
            ownProvince = bool(row)
        except Exception:
            ownProvince = False

        if not ownProvince:
            logger = logging.getLogger(__name__)
            logger.debug(
                "Unauthorized province action: user %s attempted %s on province %s",
                cId,
                way,
                province_id,
            )
            return error(400, "You don't own this province")

        allUnits = [
            "land",
            "cityCount",
            "coal_burners",
            "oil_burners",
            "hydro_dams",
            "nuclear_reactors",
            "solar_fields",
            "gas_stations",
            "general_stores",
            "farmers_markets",
            "malls",
            "banks",
            "city_parks",
            "hospitals",
            "libraries",
            "universities",
            "monorails",
            "army_bases",
            "harbours",
            "aerodomes",
            "admin_buildings",
            "silos",
            "farms",
            "pumpjacks",
            "coal_mines",
            "bauxite_mines",
            "copper_mines",
            "uranium_mines",
            "lead_mines",
            "iron_mines",
            "lumber_mills",
            "component_factories",
            "steel_mills",
            "ammunition_factories",
            "aluminium_refineries",
            "oil_refineries",
        ]

        city_units = [
            "coal_burners",
            "oil_burners",
            "hydro_dams",
            "nuclear_reactors",
            "solar_fields",
            "gas_stations",
            "general_stores",
            "farmers_markets",
            "malls",
            "banks",
            "city_parks",
            "hospitals",
            "libraries",
            "universities",
            "monorails",
        ]

        land_units = [
            "army_bases",
            "harbours",
            "aerodomes",
            "admin_buildings",
            "silos",
            "farms",
            "pumpjacks",
            "coal_mines",
            "bauxite_mines",
            "copper_mines",
            "uranium_mines",
            "lead_mines",
            "iron_mines",
            "lumber_mills",
            "component_factories",
            "steel_mills",
            "ammunition_factories",
            "aluminium_refineries",
            "oil_refineries",
        ]

        db.execute("SELECT gold FROM stats WHERE id=(%s)", (cId,))
        gold = db.fetchone()[0]

        try:
            wantedUnits = int(request.form.get(units))
        except (ValueError, TypeError):
            return error(400, "You have to enter a unit amount")

        if wantedUnits < 1:
            return error(400, "Units cannot be less than 1")

        def sum_cost_linear(
            base_price, increment_per_item, current_owned, num_purchased
        ):
            """Linear pricing: O(1) closed-form for arithmetic sum.
            Sum over i=0..n-1 of (basePrice + (currentOwned + i) * increment).
            Uses closed-form to avoid O(n) loops.
            """
            total_cost = num_purchased * base_price + increment_per_item * (
                num_purchased * current_owned + num_purchased * (num_purchased - 1) / 2
            )
            return round(total_cost)

        if units == "cityCount":
            db.execute("SELECT cityCount FROM provinces WHERE id=(%s)", (province_id,))
            current_cityCount = db.fetchone()[0]

            cityCount_price = sum_cost_linear(
                750000, 50000, current_cityCount, wantedUnits
            )
        else:
            cityCount_price = 0

        if units == "land":
            db.execute("SELECT land FROM provinces WHERE id=(%s)", (province_id,))
            current_land = db.fetchone()[0]

            land_price = sum_cost_linear(520000, 25000, current_land, wantedUnits)
        else:
            land_price = 0

        # All the unit prices in this format:
        """
        unit_price: <price of the unit>
        unit_resource (optional): {resource_name: amount}
        unit_resource2 (optional): second resource dict (if applicable)
        """
        # TODO: change the unit_resource and unit_resource2 into list based system
        unit_prices = variables.PROVINCE_UNIT_PRICES
        unit_prices["land_price"] = land_price
        unit_prices["cityCount_price"] = cityCount_price

        if units not in allUnits:
            return error("No such unit exists.", 400)

        table = "proInfra"
        if units in ["land", "cityCount"]:
            table = "provinces"

        price = unit_prices[f"{units}_price"]

        try:
            db.execute("SELECT education FROM policies WHERE user_id=%s", (cId,))
            policies = db.fetchone()[0]
        except (TypeError, IndexError):
            policies = []

        if 2 in policies:
            price *= 0.96
        if 6 in policies and units == "universities":
            price *= 0.93
        if 1 in policies and units == "universities":
            price *= 1.14

        if units not in ["cityCount", "land"]:
            totalPrice = wantedUnits * price
        else:
            totalPrice = price

        try:
            resources_data = unit_prices[f"{units}_resource"].items()
        except KeyError:
            resources_data = {}

        # Use parameterized query; avoid f-strings for column names
        if units in ["land", "cityCount"]:
            curUnStat = f"SELECT {units} FROM {table} WHERE id=%s"
        else:
            curUnStat = f"SELECT {units} FROM {table} WHERE id=%s"
        db.execute(curUnStat, (province_id,))
        currentUnits = db.fetchone()[0]

        if units in city_units:
            slot_type = "city"
        elif units in land_units:
            slot_type = "land"
        else:  # If unit is cityCount or land
            free_slots = 0
            slot_type = None

        if slot_type is not None:
            free_slots = get_free_slots(province_id, slot_type)

        def resource_stuff(resources_data, way):
            for resource, amount in resources_data:
                qty = amount * wantedUnits
                if way == "buy":
                    # Atomically subtract resource if user has enough
                    db.execute(
                        (
                            f"UPDATE resources SET {resource}={resource}-%s "
                            + f"WHERE id=%s AND {resource} >= %s RETURNING {resource}"
                        ),
                        (qty, cId, qty),
                    )
                    if db.fetchone() is None:
                        # Not enough resource
                        # Fetch current amount for informative error
                        db.execute(
                            f"SELECT {resource} FROM resources WHERE id=%s", (cId,)
                        )
                        current_resource = int(db.fetchone()[0])
                        return {
                            "fail": True,
                            "resource": resource,
                            "current_amount": current_resource,
                            "difference": current_resource - qty,
                        }

                elif way == "sell":
                    # Increment resource on sell
                    db.execute(
                        (
                            f"UPDATE resources SET {resource}={resource}+%s "
                            f"WHERE id=%s RETURNING {resource}"
                        ),
                        (qty, cId),
                    )
                    db.fetchone()

        if way == "sell":
            if wantedUnits > currentUnits:  # Checks if user has enough units to sell
                return error("You don't have enough units.", 400)

            unitUpd = f"UPDATE {table} SET {units}" + "=%s WHERE id=%s"
            db.execute(unitUpd, ((currentUnits - wantedUnits), province_id))

            # Capture gold before and perform atomic increment
            db.execute("SELECT gold FROM stats WHERE id=%s", (cId,))
            gold_before = db.fetchone()[0]

            db.execute(
                "UPDATE stats SET gold = gold + %s WHERE id = %s",
                (wantedUnits * price, cId),
            )

            db.execute("SELECT gold FROM stats WHERE id=%s", (cId,))
            gold_after = db.fetchone()[0]

            # Audit the sell event for later analysis
            create_audit_sql = (
                "CREATE TABLE IF NOT EXISTS purchase_audit ("
                "id SERIAL PRIMARY KEY, user_id INT, province_id INT, unit TEXT, "
                "units INT, gold_before BIGINT, gold_after BIGINT, note TEXT, "
                "created_at TIMESTAMP WITH TIME ZONE DEFAULT now())"
            )
            db.execute(create_audit_sql)

            insert_audit_sql = (
                "INSERT INTO purchase_audit (user_id, province_id, unit, units, "
                "gold_before, gold_after, note) VALUES (%s,%s,%s,%s,%s,%s,%s)"
            )
            db.execute(
                insert_audit_sql,
                (
                    cId,
                    province_id,
                    units,
                    wantedUnits,
                    gold_before,
                    gold_after,
                    f"sell_{units}",
                ),
            )

            # If purchase/sell is large, send a Sentry message (env-controlled)
            try:
                THRESH = int(os.getenv("PURCHASE_SENTRY_THRESHOLD", "1000000"))
                diff = abs(gold_after - gold_before)
                if diff >= THRESH:
                    try:
                        import sentry_sdk

                        with sentry_sdk.push_scope() as scope:
                            scope.set_extra("user_id", cId)
                            scope.set_extra("province_id", province_id)
                            scope.set_extra("unit", units)
                            scope.set_extra("units", wantedUnits)
                            scope.set_extra("gold_before", gold_before)
                            scope.set_extra("gold_after", gold_after)
                            msg = (
                                f"Large sell: {units} x{wantedUnits} by user {cId} "
                                f"({diff} gold)"
                            )
                            sentry_sdk.capture_message(msg)
                    except Exception:
                        pass
            except Exception:
                pass

            resource_stuff(resources_data, way)

        elif way == "buy":
            if (
                totalPrice > gold
            ):  # Checks if user wants to buy more units than he has gold
                return error("You don't have enough money.", 400)

            if free_slots < wantedUnits and units not in ["cityCount", "land"]:
                return error(400, f"Not enough {slot_type} slots for {wantedUnits}")

            res_error = resource_stuff(resources_data, way)
            if res_error:
                missing_count = res_error["difference"] * -1
                missing_res = res_error["resource"]
                return error(400, f"Missing {missing_count} {missing_res}")

            # Capture gold before and perform atomic decrement
            db.execute("SELECT gold FROM stats WHERE id=%s", (cId,))
            gold_before = db.fetchone()[0]

            db.execute("UPDATE stats SET gold=gold-%s WHERE id=(%s)", (totalPrice, cId))

            db.execute("SELECT gold FROM stats WHERE id=%s", (cId,))
            gold_after = db.fetchone()[0]

            updStat = f"UPDATE {table} SET {units}" + "=%s WHERE id=%s"
            db.execute(updStat, ((currentUnits + wantedUnits), province_id))

            # Audit the buy event
            create_audit_sql = (
                "CREATE TABLE IF NOT EXISTS purchase_audit ("
                "id SERIAL PRIMARY KEY, user_id INT, province_id INT, unit TEXT, "
                "units INT, gold_before BIGINT, gold_after BIGINT, note TEXT, "
                "created_at TIMESTAMP WITH TIME ZONE DEFAULT now())"
            )
            db.execute(create_audit_sql)

            insert_audit_sql = (
                "INSERT INTO purchase_audit (user_id, province_id, unit, units, "
                "gold_before, gold_after, note) VALUES (%s,%s,%s,%s,%s,%s,%s)"
            )
            db.execute(
                insert_audit_sql,
                (
                    cId,
                    province_id,
                    units,
                    wantedUnits,
                    gold_before,
                    gold_after,
                    f"buy_{units}",
                ),
            )

            # Sentry alert for large purchases
            try:
                THRESH = int(os.getenv("PURCHASE_SENTRY_THRESHOLD", "1000000"))
                diff = abs(gold_before - gold_after)
                if diff >= THRESH:
                    try:
                        import sentry_sdk

                        with sentry_sdk.push_scope() as scope:
                            scope.set_extra("user_id", cId)
                            scope.set_extra("province_id", province_id)
                            scope.set_extra("unit", units)
                            scope.set_extra("units", wantedUnits)
                            scope.set_extra("gold_before", gold_before)
                            scope.set_extra("gold_after", gold_after)
                            msg = (
                                f"Large buy: {units} x{wantedUnits} by user {cId} "
                                f"({diff} gold)"
                            )
                            sentry_sdk.capture_message(msg)
                    except Exception:
                        pass
            except Exception:
                pass

        if way == "buy":
            rev_type = "expense"
        elif way == "sell":
            rev_type = "revenue"

        name = f"{way.capitalize()}ing {wantedUnits} {units} in a province."
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

        # Invalidate caches for this user so UI and influence calculations reflect
        # the recent changes immediately
        try:
            invalidate_user_cache(cId)
        except Exception:
            pass

        # Also invalidate page-level caches (provinces list and province pages)
        # so the UI reflects the new units/land immediately instead of waiting
        # for TTL expiry.
        try:
            from database import query_cache

            query_cache.invalidate(pattern=f"provinces_{cId}_")
            query_cache.invalidate(pattern=f"province_{cId}_")
        except Exception:
            pass

    return redirect(f"/province/{province_id}")
