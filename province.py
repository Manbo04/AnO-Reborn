from flask import Blueprint, request, render_template, session, redirect
from helpers import login_required, error
from dotenv import load_dotenv
import variables
from helpers import get_date
from database import get_db_cursor, cache_response, invalidate_user_cache
import os
import math
from action_loop import build_structure, ActionLoopError, BUILD_COST_RESOURCE

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

        # Combined query for province + stats (legacy resources/proInfra tables removed)
        db.execute(
            """
            SELECT p.id, p.userId AS user, p.provinceName AS name, p.population,
                   p.pollution, p.happiness, p.productivity, p.consumer_spending,
                   CAST(p.citycount AS INTEGER) as citycount,
                   p.land, p.energy AS electricity,
                   s.location,
                   COALESCE(p.pop_children, 0) AS pop_children,
                   COALESCE(p.pop_working, 0) AS pop_working,
                   COALESCE(p.pop_elderly, 0) AS pop_elderly
            FROM provinces p
            LEFT JOIN stats s ON p.userId = s.id
            WHERE p.id = %s
            """,
            (pId,),
        )
        result = db.fetchone()

        if not result:
            return error(404, "Province doesn't exist")

        # Convert to dict for template
        result = dict(result)

        # Get upgrades in normalized schema
        user_id = result["user"]
        cache_key = f"upgrades_{user_id}"
        upgrades = query_cache.get(cache_key)
        if upgrades is None:
            legacy_upgrade_to_tech = {
                "betterengineering": "better_engineering",
                "cheapermaterials": "cheaper_materials",
                "onlineshopping": "online_shopping",
                "governmentregulation": "government_regulation",
                "nationalhealthinstitution": "national_health_institution",
                "highspeedrail": "high_speed_rail",
                "advancedmachinery": "advanced_machinery",
                "strongerexplosives": "stronger_explosives",
                "widespreadpropaganda": "widespread_propaganda",
                "increasedfunding": "increased_funding",
                "automationintegration": "automation_integration",
                "largerforges": "larger_forges",
                "lootingteams": "looting_teams",
                "organizedsupplylines": "organized_supply_lines",
                "largestorehouses": "large_storehouses",
                "ballisticmissilesilo": "ballistic_missile_silo",
                "icbmsilo": "icbm_silo",
                "nucleartestingfacility": "nuclear_testing_facility",
            }
            tech_to_legacy = {v: k for k, v in legacy_upgrade_to_tech.items()}
            upgrades = {k: False for k in legacy_upgrade_to_tech.keys()}
            db.execute(
                """
                SELECT td.name
                FROM user_tech ut
                JOIN tech_dictionary td ON td.tech_id = ut.tech_id
                WHERE ut.user_id=%s AND ut.is_unlocked=TRUE
                """,
                (user_id,),
            )
            for (tech_name,) in db.fetchall():
                legacy_key = tech_to_legacy.get(tech_name)
                if legacy_key:
                    upgrades[legacy_key] = True
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

        # Build units dict from user_buildings (Economy 2.0 normalized schema)
        # Maps building name → quantity owned by this user
        db.execute(
            """
            SELECT bd.name, COALESCE(ub.quantity, 0) AS quantity
            FROM building_dictionary bd
            LEFT JOIN user_buildings ub
                ON ub.building_id = bd.building_id AND ub.user_id = %s
            WHERE bd.is_active = TRUE
            """,
            (user_id,),
        )
        units = {row["name"]: row["quantity"] for row in db.fetchall()}
        # Ensure all expected building names exist in units (default 0)
        all_building_names = [
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
            "distribution_centers",
            "industrial_district",
            "primary_school",
            "high_school",
        ]
        for bname in all_building_names:
            units.setdefault(bname, 0)

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
            "distribution_centers",
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

        # Check consumer goods and rations from normalized economy data
        db.execute(
            """
            SELECT rd.name, ue.quantity
            FROM user_economy ue
            JOIN resource_dictionary rd ON rd.resource_id = ue.resource_id
            WHERE ue.user_id=%s AND rd.name IN ('consumer_goods', 'rations')
            """,
            (user_id,),
        )
        economy_values = {row["name"]: row["quantity"] for row in db.fetchall()}
        consumer_goods = economy_values.get("consumer_goods", 0) or 0
        rations = economy_values.get("rations", 0) or 0

        max_cg = math.ceil(province["population"] / variables.CONSUMER_GOODS_PER)
        enough_consumer_goods = consumer_goods >= max_cg

        rations_minus = province["population"] // variables.RATIONS_PER
        if variables.FEATURE_RATIONS_DISTRIBUTION:
            from tasks import rations_distribution_capacity

            # distribution cap for entire user; we require at least the
            # province consumption to have rations available here
            dist_cap = rations_distribution_capacity(cId) or 0
            enough_rations = (rations - rations_minus > 1) and (
                dist_cap >= rations_minus
            )
        else:
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

        # Normalized buildings (for Action Loop quick-build form)
        db.execute(
            """
            SELECT building_id, display_name, base_cost
            FROM building_dictionary
            WHERE is_active = TRUE
            ORDER BY display_name ASC
            """
        )
        normalized_buildings = db.fetchall() or []

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
            normalized_buildings=normalized_buildings,
            build_cost_resource=BUILD_COST_RESOURCE,
            distribution_capacity=(
                dist_cap if variables.FEATURE_RATIONS_DISTRIBUTION else None
            ),
        )


@bp.route("/build_structure", methods=["POST"])
@login_required
def build_structure_action():
    cId = session["user_id"]
    province_id = request.form.get("province_id")

    try:
        building_id = int(request.form.get("building_id", "0"))
        quantity = int(request.form.get("quantity", "1"))
    except (TypeError, ValueError):
        return error(400, "Invalid building selection or quantity.")

    try:
        build_structure(cId, building_id, quantity)
    except ActionLoopError as e:
        return error(400, str(e))

    try:
        invalidate_user_cache(cId)
    except Exception:
        pass

    if province_id:
        return redirect(f"/province/{province_id}")
    return redirect(f"/country/id={cId}")


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
                db.fetchone()  # Consume result

                # No need to INSERT INTO proInfra - user_buildings is populated
                # dynamically when buildings are purchased

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
        # Get user_id from province
        db.execute("SELECT userId FROM provinces WHERE id=%s", (pId,))
        user_id_row = db.fetchone()
        if not user_id_row:
            return 0
        user_id = user_id_row[0]

        if slot_type == "city":
            # Query normalized user_buildings for city buildings
            db.execute(
                """
                SELECT COALESCE(SUM(ub.quantity), 0)
                FROM user_buildings ub
                JOIN building_dictionary bd ON bd.building_id = ub.building_id
                WHERE ub.user_id = %s
                  AND bd.name IN (
                    'coal_burners', 'oil_burners', 'hydro_dams',
                    'nuclear_reactors', 'solar_fields', 'gas_stations',
                    'general_stores', 'farmers_markets', 'malls', 'banks',
                    'distribution_centers', 'city_parks', 'hospitals',
                    'libraries', 'universities', 'monorails'
                  )
                """,
                (user_id,),
            )
            used_slots = int(db.fetchone()[0])

            db.execute("SELECT cityCount FROM provinces WHERE id=%s", (pId,))
            all_slots = int(db.fetchone()[0])

            free_slots = all_slots - used_slots

        elif slot_type == "land":
            # Query normalized user_buildings for land buildings
            db.execute(
                """
                SELECT COALESCE(SUM(ub.quantity), 0)
                FROM user_buildings ub
                JOIN building_dictionary bd ON bd.building_id = ub.building_id
                WHERE ub.user_id = %s
                  AND bd.name IN (
                    'army_bases', 'harbours', 'aerodomes', 'admin_buildings',
                    'silos', 'farms', 'pumpjacks', 'coal_mines', 'bauxite_mines',
                    'copper_mines', 'uranium_mines', 'lead_mines', 'iron_mines',
                    'lumber_mills', 'component_factories', 'steel_mills',
                    'ammunition_factories', 'aluminium_refineries', 'oil_refineries'
                  )
                """,
                (user_id,),
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
            "distribution_centers",
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
            "distribution_centers",
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

        # Parameterized query: buildings use user_buildings,
        # land/city use provinces
        if units in ["land", "cityCount"]:
            curUnStat = f"SELECT {units} FROM provinces WHERE id=%s"
            db.execute(curUnStat, (province_id,))
            currentUnits = db.fetchone()[0]
        else:
            # Economy 2.0: building counts stored in user_buildings
            db.execute(
                """
                SELECT COALESCE(ub.quantity, 0)
                FROM building_dictionary bd
                LEFT JOIN user_buildings ub
                    ON ub.building_id = bd.building_id AND ub.user_id = %s
                WHERE bd.name = %s
                """,
                (cId, units),
            )
            row = db.fetchone()
            currentUnits = row[0] if row else 0

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
                    # Get resource_id for the resource name
                    db.execute(
                        "SELECT resource_id FROM resource_dictionary WHERE name = %s",
                        (resource,),
                    )
                    resource_id_row = db.fetchone()
                    if not resource_id_row:
                        return {
                            "fail": True,
                            "resource": resource,
                            "current_amount": 0,
                            "difference": -qty,
                        }
                    resource_id = resource_id_row[0]

                    # Atomically subtract resource if user has enough
                    db.execute(
                        (
                            "UPDATE user_economy SET quantity = quantity - %s "
                            "WHERE user_id = %s AND resource_id = %s AND "
                            "quantity >= %s RETURNING quantity"
                        ),
                        (qty, cId, resource_id, qty),
                    )
                    if db.fetchone() is None:
                        # Not enough resource
                        # Fetch current amount for informative error from user_economy
                        db.execute(
                            """
                            SELECT COALESCE(ue.quantity, 0)
                            FROM user_economy ue
                            JOIN resource_dictionary rd
                                ON rd.resource_id = ue.resource_id
                            WHERE ue.user_id = %s AND rd.name = %s
                            """,
                            (cId, resource),
                        )
                        row = db.fetchone()
                        current_resource = int(row[0]) if row else 0
                        return {
                            "fail": True,
                            "resource": resource,
                            "current_amount": current_resource,
                            "difference": current_resource - qty,
                        }

                elif way == "sell":
                    # Get resource_id for the resource name
                    db.execute(
                        "SELECT resource_id FROM resource_dictionary WHERE name = %s",
                        (resource,),
                    )
                    resource_id_row = db.fetchone()
                    if not resource_id_row:
                        continue  # Skip if resource doesn't exist
                    resource_id = resource_id_row[0]

                    # Increment resource on sell
                    db.execute(
                        (
                            "UPDATE user_economy SET quantity = quantity + %s "
                            "WHERE user_id = %s AND resource_id = %s "
                            "RETURNING quantity"
                        ),
                        (qty, cId, resource_id),
                    )
                    db.fetchone()

        if way == "sell":
            if wantedUnits > currentUnits:  # Checks if user has enough units to sell
                return error("You don't have enough units.", 400)

            if units in ["land", "cityCount"]:
                unitUpd = f"UPDATE provinces SET {units}=%s WHERE id=%s"
                db.execute(unitUpd, ((currentUnits - wantedUnits), province_id))
            else:
                # Economy 2.0: decrement user_buildings
                db.execute(
                    """
                    UPDATE user_buildings SET quantity = quantity - %s
                    WHERE user_id = %s
                      AND building_id = (
                          SELECT building_id FROM building_dictionary WHERE name = %s
                      )
                    """,
                    (wantedUnits, cId, units),
                )

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

            if units in ["land", "cityCount"]:
                updStat = f"UPDATE provinces SET {units}=%s WHERE id=%s"
                db.execute(updStat, ((currentUnits + wantedUnits), province_id))
            else:
                # Economy 2.0: increment user_buildings
                db.execute(
                    """
                    UPDATE user_buildings SET quantity = quantity + %s
                    WHERE user_id = %s
                      AND building_id = (
                          SELECT building_id FROM building_dictionary WHERE name = %s
                      )
                    """,
                    (wantedUnits, cId, units),
                )

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
