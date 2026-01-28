from flask import request, render_template, session, redirect
from helpers import login_required
from helpers import get_influence, error
from tasks import calc_pg, calc_ti, rations_needed
import os
import variables
from dotenv import load_dotenv
from collections import defaultdict
from policies import get_user_policies
from operator import itemgetter
from datetime import datetime
from wars.service import target_data
import math
from database import get_db_cursor, cache_response

load_dotenv()

# App config will be set when routes are registered


# TODO: rewrite this function for fucks sake
def get_econ_statistics(cId):
    from database import get_db_cursor, query_cache
    from psycopg2.extras import RealDictCursor

    # Check cache first
    cache_key = f"econ_stats_{cId}"
    cached = query_cache.get(cache_key)
    if cached is not None:
        return cached

    with get_db_cursor(cursor_factory=RealDictCursor) as dbdict:
        # TODO: less loc
        try:
            dbdict.execute(
                """
            SELECT
            SUM(proInfra.coal_burners) AS coal_burners,
            SUM(proInfra.oil_burners) AS oil_burners,
            SUM(proInfra.hydro_dams) AS hydro_dams ,
            SUM(proInfra.nuclear_reactors) AS nuclear_reactors,
            SUM(proInfra.solar_fields) AS solar_fields,
            SUM(proInfra.gas_stations) AS gas_stations,
            SUM(proInfra.general_stores) AS general_stores,
            SUM(proInfra.farmers_markets) AS farmers_markets,
            SUM(proInfra.malls) AS malls,
            SUM(proInfra.banks) AS banks,
            SUM(proInfra.city_parks) AS city_parks,
            SUM(proInfra.hospitals) AS hospitals,
            SUM(proInfra.libraries) AS libraries,
            SUM(proInfra.universities) AS universities,
            SUM(proInfra.monorails) AS monorails,
            SUM(proInfra.army_bases) AS army_bases,
            SUM(proInfra.harbours) AS harbours,
            SUM(proInfra.aerodomes) AS aerodomes,
            SUM(proInfra.admin_buildings) AS admin_buildings,
            SUM(proInfra.silos) AS silos,
            SUM(proInfra.farms) AS farms,
            SUM(proInfra.pumpjacks) AS pumpjacks,
            SUM(proInfra.coal_mines) AS coal_mines,
            SUM(proInfra.bauxite_mines) AS bauxite_mines,
            SUM(proInfra.copper_mines) AS copper_mines,
            SUM(proInfra.uranium_mines) AS uranium_mines,
            SUM(proInfra.lead_mines) AS lead_mines,
            SUM(proInfra.iron_mines) AS iron_mines,
            SUM(proInfra.lumber_mills) AS lumber_mills,
            SUM(proInfra.component_factories) AS component_factories,
            SUM(proInfra.steel_mills) AS steel_mills,
            SUM(proInfra.ammunition_factories) AS ammunition_factories,
            SUM(proInfra.aluminium_refineries) AS aluminium_refineries,
            SUM(proInfra.oil_refineries) AS oil_refineries
            FROM proInfra LEFT JOIN provinces ON provinces.id=proInfra.id
            WHERE provinces.userId=%s;
            """,
                (cId,),
            )
            total = dict(dbdict.fetchone())
        except (TypeError, AttributeError, KeyError):
            total = {}

    expenses = {}
    expenses = defaultdict(lambda: defaultdict(lambda: 0), expenses)

    def get_unit_type(unit):
        for type_name, buildings in variables.INFRA_TYPE_BUILDINGS.items():
            if unit in buildings:
                return type_name

    def check_for_resource_upkeep(unit, amount):
        try:
            convert_minus = list(variables.INFRA[f"{unit}_convert_minus"][0].items())[0]
            minus = convert_minus[0]
            minus_amount = convert_minus[1] * amount
        except KeyError:
            minus, minus_amount = [None, None]
            convert_minus = []
            return False

        if minus is not None:
            unit_type = get_unit_type(unit)
            expenses[unit_type][minus] += minus_amount
        return True

    def check_for_monetary_upkeep(unit, amount):
        operating_costs = int(variables.INFRA[f"{unit}_money"]) * amount
        unit_type = get_unit_type(unit)
        expenses[unit_type]["money"] += operating_costs

    for unit, amount in total.items():
        if amount != 0 and amount is not None:
            check_for_resource_upkeep(unit, amount)
            check_for_monetary_upkeep(unit, amount)

    # Cache the result
    query_cache.set(cache_key, expenses)
    return expenses


def format_econ_statistics(statistics):
    formatted = {}
    formatted = defaultdict(lambda: "", formatted)

    for unit_type, unit_type_data in statistics.items():
        unit_type_data = list(unit_type_data.items())
        idx = 0
        for resource, amount in unit_type_data:
            amount = "{:,}".format(amount)

            if idx != len(unit_type_data) - 1:
                expense_string = f"{amount} {resource}, "
            else:
                expense_string = f"{amount} {resource}"

            if (
                resource == "money"
            ):  # Bit of a hack but the simplest and cleanest approach
                expense_string = expense_string.replace(" money", "")

            formatted[unit_type] += expense_string
            idx += 1

    return formatted


def get_revenue(cId):
    from database import get_db_connection, query_cache
    from psycopg2.extras import RealDictCursor  # noqa: F401

    # Check cache first - expensive calculation
    cache_key = f"revenue_{cId}"
    cached = query_cache.get(cache_key)
    if cached is not None:
        return cached

    # Use a dedicated connection for the lifetime of this function to
    # prevent nested `get_db_cursor()` calls from accidentally reusing
    # the same pooled connection (and closing a cursor prematurely).
    with get_db_connection() as conn:
        db = conn.cursor()

        _ = cg_need(cId)

        # Prefetch province ids, land and productivity
        # to avoid per-province lookups later
        db.execute(
            "SELECT id, land, productivity FROM provinces WHERE userId=%s",
            (cId,),
        )
        province_rows = db.fetchall()
        provinces = [row[0] for row in province_rows]
        land_by_id = {row[0]: row[1] for row in province_rows}
        prod_by_id = {row[0]: row[2] for row in province_rows}

        revenue = {"gross": {}, "gross_theoretical": {}, "net": {}}

        infra = variables.NEW_INFRA
        # Copy to avoid mutating global state; repeated extends were exploding the list
        resources = list(variables.RESOURCES)
        resources.extend(["money", "energy"])
        for resource in resources:
            revenue["gross"][resource] = 0
            revenue["gross_theoretical"][resource] = 0
            revenue["net"][resource] = 0

        # Define proinfra columns once (outside loop)
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

        # OPTIMIZATION: Batch fetch all proInfra data in ONE query instead of N queries
        proinfra_by_id = {}
        if provinces:
            placeholders = ",".join(["%s"] * len(provinces))
            db.execute(
                f"SELECT * FROM proInfra WHERE id IN ({placeholders})", tuple(provinces)
            )
            for row in db.fetchall():
                proinfra_by_id[row[0]] = dict(zip(proinfra_columns, row))

        for province in provinces:
            buildings = proinfra_by_id.get(province)
            if buildings is None:
                buildings = dict(zip(proinfra_columns, [0] * len(proinfra_columns)))

            for building, build_count in buildings.items():
                if building == "id":
                    continue
                if build_count is None or build_count == 0:
                    continue

                operating_costs = infra[building]["money"] * build_count
                revenue["net"]["money"] -= operating_costs

                plus = infra[building].get("plus", {})
                for resource, amount in plus.items():
                    if building == "farms":
                        land = land_by_id.get(province, 0)
                        amount += land * variables.LAND_FARM_PRODUCTION_ADDITION

                    # Compute theoretical production (no productivity multiplier)
                    theoretical_total = build_count * amount

                    # Apply productivity multiplier to match actual generation behavior
                    productivity = prod_by_id.get(province, 50)
                    if productivity is not None:
                        multiplier = (
                            1
                            + (productivity - 50)
                            * variables.DEFAULT_PRODUCTIVITY_PRODUCTION_MUTLIPLIER
                        )
                    else:
                        multiplier = 1

                    adjusted_total = build_count * amount * multiplier
                    # Normalize to integer to mirror production rounding
                    adjusted_total = math.ceil(adjusted_total)

                    # Record both the theoretical (original-style)
                    # and the actual (projected) values
                    revenue["gross_theoretical"][resource] += theoretical_total
                    revenue["gross"][resource] += adjusted_total
                    revenue["net"][resource] += adjusted_total

                minus = infra[building].get("minus", {})
                for resource, amount in minus.items():
                    total = build_count * amount
                    revenue["net"][resource] -= total

        db.execute("SELECT rations FROM resources WHERE id=%s", (cId,))
        current_rations = db.fetchone()[0]

        ti_money, ti_cg = calc_ti(cId)

        # Updates money
        revenue["gross"]["money"] += ti_money
        revenue["net"]["money"] += ti_money

        revenue["net"]["consumer_goods"] += ti_cg

        prod_rations = revenue["gross"]["rations"]
        new_rations = next_turn_rations(cId, prod_rations)
        revenue["net"]["rations"] = new_rations - current_rations

        # Filter to only show resources with positive gross production
        # or non-zero net (for special cases like rations)
        filtered_revenue = {"gross": revenue["gross"], "net": revenue["net"]}

        return filtered_revenue


def next_turn_rations(cId, prod_rations):
    from database import get_db_connection

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT id FROM provinces WHERE userId=%s", (cId,))
        provinces = db.fetchall()

        db.execute("SELECT rations FROM resources WHERE id=%s", (cId,))
        current_rations = db.fetchone()[0] + prod_rations

        for pId in provinces:
            rations, _ = calc_pg(pId, current_rations)
            current_rations = rations

        return current_rations


def delete_news(id):
    with get_db_cursor() as db:
        db.execute("SELECT destination_id FROM news WHERE id=(%s)", (id,))
        destination_id = db.fetchone()[0]
        if destination_id == session["user_id"]:
            db.execute("DELETE FROM news WHERE id=(%s)", (id,))
            return "200"
        else:
            return "403"


# The amount of consumer goods a player needs to fill up fully


def cg_need(user_id):
    from database import get_db_connection

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT SUM(population) FROM provinces WHERE userId=%s", (user_id,))
        population = db.fetchone()[0]
        if population is None:
            population = 0

        # How many consumer goods are needed to feed a nation
        cg_needed = math.ceil(population / variables.CONSUMER_GOODS_PER)

        return cg_needed


@login_required
def my_country():
    user_id = session.get("user_id")
    return redirect(f"/country/id={user_id}")


def country(cId):
    with get_db_cursor() as db:
        db.execute(
            "SELECT users.username, stats.location, users.description, "
            "users.date, users.flag "
            "FROM users INNER JOIN stats ON users.id=stats.id WHERE users.id=%s",
            (cId,),
        )
        row = db.fetchone()
        if not row:
            return error(404, "Country doesn't exist")
        username, location, description, dateCreated, flag = row

        policies = get_user_policies(cId)
        influence = get_influence(cId)

        db.execute(
            "SELECT SUM(population), AVG(happiness), AVG(productivity), COUNT(id) "
            "FROM provinces WHERE userId=%s",
            (cId,),
        )
        stats_row = db.fetchone()
        if stats_row:
            population, happiness, productivity, provinceCount = stats_row
        else:
            population = 0
            happiness = 0
            productivity = 0
            provinceCount = 0

        db.execute(
            "SELECT provinceName, id, population, "
            "CAST(cityCount AS INTEGER) as cityCount, "
            "land, happiness, productivity "
            "FROM provinces WHERE userId=(%s) "
            "ORDER BY id ASC",
            (cId,),
        )
        provinces = db.fetchall()

        cg_needed = cg_need(cId)

        try:
            status = cId == str(session["user_id"])
        except (KeyError, TypeError):
            status = False

        db.execute(
            "SELECT coalitions.colId, coalitions.role, "
            "colNames.name, colNames.flag "
            "FROM coalitions INNER JOIN colNames ON coalitions.colId=colNames.id "
            "WHERE coalitions.userId=%s",
            (cId,),
        )
        col_row = db.fetchone()
        if col_row:
            colId, colRole, colName, colFlag = col_row
        else:
            colId = 0
            colRole = None
            colName = ""
            colFlag = None

        spy = {}
        uId = session.get("user_id")
        if uId:
            db.execute("SELECT spies FROM military WHERE military.id=(%s)", (uId,))
            spy["count"] = db.fetchone()[0]
        else:
            spy["count"] = 0

        # News page
        idd = int(cId)
        news = []
        news_amount = 0
        if idd == session["user_id"]:
            # TODO: handle this as country/id=<int:cId>
            db.execute(
                "SELECT message,date,id FROM news WHERE destination_id=(%s)", (cId,)
            )
            # data order in the tuple appears as in the news schema
            # (notice this when working with this data using jinja)
            news = db.fetchall()
            news_amount = len(news)

        # Revenue stuff
        if status:
            revenue = get_revenue(cId)
            db.execute(
                "SELECT name, type, resource, amount, date "
                "FROM revenue WHERE user_id=%s",
                (cId,),
            )
            expenses = db.fetchall()

            statistics = get_econ_statistics(cId)
            statistics = format_econ_statistics(statistics)
        else:
            revenue = {}
            expenses = []
            statistics = {}

        rations_need = rations_needed(cId)

    return render_template(
        "country.html",
        username=username,
        cId=cId,
        description=description,
        happiness=happiness,
        population=population,
        location=location,
        status=status,
        provinceCount=provinceCount,
        colName=colName,
        dateCreated=dateCreated,
        influence=influence,
        provinces=provinces,
        colId=colId,
        flag=flag,
        spy=spy,
        colFlag=colFlag,
        colRole=colRole,
        productivity=productivity,
        revenue=revenue,
        news=news,
        news_amount=news_amount,
        cg_needed=cg_needed,
        rations_need=rations_need,
        expenses=expenses,
        statistics=statistics,
        policies=policies,
    )


def countries():
    with get_db_cursor() as db:
        cId = session["user_id"]

        search = request.values.get("search")
        lowerinf = request.values.get("lowerinf")
        upperinf = request.values.get("upperinf")
        province_range = request.values.get("province_range")
        sort = request.values.get("sort")
        sortway = request.values.get("sortway")
        page = request.values.get("page", default=1, type=int)

        if sort == "war_range":
            target = target_data(cId)
            lowerinf = target["lower"]
            upperinf = target["upper"]
            province_range = target["province_range"]

        if not province_range:
            province_range = 0

        # First, get total count without pagination for result info
        db.execute(
            """SELECT COUNT(DISTINCT users.id) as total
FROM USERS
LEFT JOIN provinces ON users.id = provinces.userId
LEFT JOIN coalitions ON users.id = coalitions.userId
LEFT JOIN colNames ON colNames.id = coalitions.colId
GROUP BY users.id
HAVING COUNT(provinces.id) >= %s;""",
            (province_range,),
        )
        try:
            total_count = db.fetchone()[0]
        except (TypeError, IndexError):
            total_count = 0

        # Fetch paginated results with optimized query
        page_size = 50
        offset = (page - 1) * page_size

        db.execute(
            """
            SELECT users.id,
                   users.username,
                   users.date,
                   users.flag,
                   COALESCE(SUM(provinces.population), 0) AS province_population,
                   coalitions.colId,
                   colNames.name,
                   COUNT(provinces.id) as provinces_count
            FROM USERS
            LEFT JOIN provinces ON users.id = provinces.userId
            LEFT JOIN coalitions ON users.id = coalitions.userId
            LEFT JOIN colNames ON colNames.id = coalitions.colId
            GROUP BY users.id, coalitions.colId, colNames.name
            HAVING COUNT(provinces.id) >= %s
            ORDER BY users.id DESC
            LIMIT %s OFFSET %s;
            """,
            (province_range, page_size, offset),
        )
        dbResults = db.fetchall()

    # Batch load all influence values for this page using bulk query (single DB call)
    from helpers import get_bulk_influence

    user_ids = [user[0] for user in dbResults]
    influences = get_bulk_influence(user_ids)

    # Process results with cached influences
    results = []
    for user in dbResults:
        addUser = True
        user_id = user[0]
        user = list(user)
        influence = influences.get(user_id, 0)

        user_date = user[2]
        date = datetime.fromisoformat(user_date)
        unix = int((date - datetime(1970, 1, 1)).total_seconds())

        user.append(influence)
        user.append(unix)
        if search and search not in user[1]:  # user[1] - username
            addUser = False
        if lowerinf and influence < float(lowerinf):
            addUser = False
        if upperinf and influence > float(upperinf):
            addUser = False
        if province_range and user[7] > int(province_range):  # user[7] - province count
            addUser = False

        if addUser:
            results.append(user)

    if not sort:
        sortway = "desc"
        sort = "influence"

    reverse = False
    if sortway == "desc":
        reverse = True
    if sort == "influence":
        results = sorted(results, key=itemgetter(8), reverse=reverse)
    if sort == "age":
        results = sorted(results, key=itemgetter(9), reverse=reverse)
    if sort == "population":
        results = sorted(results, key=itemgetter(4), reverse=reverse)
    if sort == "provinces":
        results = sorted(results, key=itemgetter(7), reverse=reverse)

    total_pages = (total_count + page_size - 1) // page_size
    return render_template(
        "countries.html",
        countries=results,
        current_user_id=cId,
        current_page=page,
        total_pages=total_pages,
        sort=sort,
        sortway=sortway,
        search=search,
        lowerinf=lowerinf,
        upperinf=upperinf,
        province_range=province_range,
    )


def update_info():
    with get_db_cursor() as db:
        cId = session["user_id"]

        # Description changing
        description = request.form["description"]

        if description not in ["None", ""]:
            db.execute(
                "UPDATE users SET description=%s WHERE id=%s", (description, cId)
            )

        # Flag changing
        ALLOWED_EXTENSIONS = ["png", "jpg", "jpeg"]

        def allowed_file(filename):
            return (
                "." in filename
                and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
            )

        flag = request.files.get("flag_input")
        if flag and flag.filename:  # Check both file exists AND has a filename
            if not allowed_file(flag.filename):
                return error(400, "Bad flag file format")

            current_filename = flag.filename

            try:
                db.execute("SELECT flag FROM users WHERE id=(%s)", (cId,))
                current_flag = db.fetchone()[0]
                from flask import current_app

                os.remove(
                    os.path.join(current_app.config["UPLOAD_FOLDER"], current_flag)
                )
            except (OSError, TypeError, AttributeError):
                pass

            # Save the file & store in database for persistent storage
            if allowed_file(current_filename):
                from flask import current_app
                from database import query_cache
                from helpers import compress_flag_image

                # Compress and resize flag for fast storage/retrieval
                flag_data, extension = compress_flag_image(
                    flag, max_size=300, quality=85
                )
                filename = f"flag_{cId}.{extension}"

                db.execute(
                    "UPDATE users SET flag=(%s), flag_data=(%s) WHERE id=(%s)",
                    (filename, flag_data, cId),
                )

                # Also save to filesystem for backward compatibility
                flag.seek(0)  # Reset file pointer after read
                new_path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
                flag.save(new_path)

                # Invalidate flag cache so new flag shows immediately
                query_cache.invalidate(f"flag_{cId}")

        """
        bg_flag = request.files["bg_flag_input"]
        if bg_flag and allowed_file(bg_flag.filename):


            # Check if the user already has a flag
            try:
                db.execute("SELECT bg_flag FROM users WHERE id=(%s)", (cId,))
                current_bg_flag = db.fetchone()[0]

                os.remove(os.path.join(
                    current_app.config['UPLOAD_FOLDER'], current_bg_flag))
            except FileNotFoundError:
                pass

            # Save the file & shit
            current_filename = bg_flag.filename
            if allowed_file(current_filename):
                extension = current_filename.rsplit('.', 1)[1].lower()
                filename = f"bg_flag_{cId}" + '.' + extension
                flag.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
                db.execute("UPDATE users SET bg_flag=(%s) WHERE id=(%s)",
                           (filename, cId))
        """

        # Location changing
        new_location = request.form.get("countryLocation")

        continents = [
            "Tundra",
            "Savanna",
            "Desert",
            "Jungle",
            "Boreal Forest",
            "Grassland",
            "Mountain Range",
        ]

        if new_location not in continents and new_location not in ["", "none"]:
            return error(400, "No such continent")

        if new_location not in ["", "none"]:
            db.execute("SELECT id FROM provinces WHERE userId=%s", (cId,))
            provinces = db.fetchall()

            # OPTIMIZATION: Batch update all provinces in ONE query instead of N queries
            if provinces:
                province_ids = [p[0] for p in provinces]
                placeholders = ",".join(["%s"] * len(province_ids))
                sql = (
                    "UPDATE proInfra SET pumpjacks=0, coal_mines=0, bauxite_mines=0, "
                    "copper_mines=0, uranium_mines=0, lead_mines=0, iron_mines=0, "
                    "lumber_mills=0 WHERE id IN ({placeholders})"
                )
                db.execute(sql.format(placeholders=placeholders), tuple(province_ids))
            db.execute("UPDATE stats SET location=%s WHERE id=%s", (new_location, cId))

    return redirect(f"/country/id={cId}")  # Redirects the user to his country


# TODO: check if you can DELETE with one statement
def delete_own_account():
    with get_db_cursor() as db:
        cId = session["user_id"]

        # Track how many rows we delete from key tables for observability
        deleted_counts = {}

        # Deletes all the info from database created upon signup
        db.execute("DELETE FROM users WHERE id=(%s)", (cId,))
        deleted_counts["users"] = db.rowcount
        db.execute("DELETE FROM stats WHERE id=(%s)", (cId,))
        deleted_counts["stats"] = db.rowcount
        db.execute("DELETE FROM military WHERE id=(%s)", (cId,))
        deleted_counts["military"] = db.rowcount
        db.execute("DELETE FROM resources WHERE id=(%s)", (cId,))
        deleted_counts["resources"] = db.rowcount

        # Deletes all market things the user is associated with
        db.execute("DELETE FROM offers WHERE user_id=(%s)", (cId,))
        deleted_counts["offers"] = db.rowcount
        db.execute("DELETE FROM wars WHERE defender=%s OR attacker=%s", (cId, cId))
        deleted_counts["wars"] = db.rowcount

        # Deletes all the users provinces and their infrastructure
        # OPTIMIZATION: Batch delete instead of N+1 queries
        db.execute("SELECT id FROM provinces WHERE userId=%s", (cId,))
        province_ids = db.fetchall()
        if province_ids:
            ids = [p[0] for p in province_ids]
            placeholders = ",".join(["%s"] * len(ids))
            db.execute(
                f"DELETE FROM provinces WHERE id IN ({placeholders})", tuple(ids)
            )
            deleted_counts["provinces"] = db.rowcount
            db.execute(f"DELETE FROM proInfra WHERE id IN ({placeholders})", tuple(ids))
            deleted_counts["proInfra"] = db.rowcount

        db.execute("DELETE FROM upgrades WHERE user_id=%s", (cId,))
        deleted_counts["upgrades"] = db.rowcount
        db.execute("DELETE FROM trades WHERE offeree=%s OR offerer=%s", (cId, cId))
        deleted_counts["trades"] = db.rowcount
        db.execute("DELETE FROM spyinfo WHERE spyer=%s OR spyee=%s", (cId, cId))
        deleted_counts["spyinfo"] = db.rowcount
        db.execute("DELETE FROM requests WHERE reqId=%s", (cId,))
        deleted_counts["requests"] = db.rowcount
        db.execute("DELETE FROM reparation_tax WHERE loser=%s OR winner=%s", (cId, cId))
        deleted_counts["reparation_tax"] = db.rowcount
        db.execute("DELETE FROM peace WHERE author=%s", (cId,))
        deleted_counts["peace"] = db.rowcount

        try:
            from coalitions import get_user_role

            coalition_role = get_user_role(cId)
        except Exception:
            coalition_role = None
        if coalition_role != "leader":
            pass
        else:
            db.execute("SELECT colId FROM coalitions WHERE userId=%s", (cId,))
            user_coalition = db.fetchone()[0]

            db.execute(
                "SELECT COUNT(userId) FROM coalitions WHERE role='leader' AND colId=%s",
                (user_coalition,),
            )
            leader_count = db.fetchone()[0]

            if leader_count != 1:
                pass
            else:
                db.execute("DELETE FROM coalitions WHERE colId=%s", (user_coalition,))
                db.execute("DELETE FROM colNames WHERE id=%s", (user_coalition,))
                db.execute("DELETE FROM colBanks WHERE colid=%s", (user_coalition,))
                db.execute("DELETE FROM requests WHERE colId=%s", (user_coalition,))

        db.execute("DELETE FROM coalitions WHERE userId=%s", (cId,))
        db.execute("DELETE FROM colBanksRequests WHERE reqId=%s", (cId,))

        try:
            import logging

            logging.getLogger(__name__).info(
                "delete_own_account: deleted_counts=%s", deleted_counts
            )
        except Exception:
            pass

    session.clear()

    return redirect("/")


def register_countries_routes(app_instance):
    """Register all routes from countries module after app initialization."

    This deferred registration avoids circular imports:
    wsgi.py -> app.py -> countries -> app (causes circular dependency at import time)

    Args:
        app_instance: Flask app instance to register routes with
    """
    # Configure app settings for countries routes
    app_instance.config["UPLOAD_FOLDER"] = "static/flags"
    app_instance.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024  # 2 MB limit

    # Register my_country route
    app_instance.add_url_rule(
        "/my_country", "my_country", login_required(my_country), methods=["GET"]
    )

    # Register country route
    # Cache is short (30s) since users viewing their own country
    # need fresh data after edits
    app_instance.add_url_rule(
        "/country/id=<cId>",
        "country",
        login_required(cache_response(ttl_seconds=30)(country)),
        methods=["GET"],
    )

    # Register countries route (cached for 60 seconds - list doesn't change often)
    app_instance.add_url_rule(
        "/countries",
        "countries",
        login_required(cache_response(ttl_seconds=60)(countries)),
        methods=["GET"],
    )

    # Register update_country_info route
    app_instance.add_url_rule(
        "/update_country_info",
        "update_info",
        login_required(update_info),
        methods=["POST"],
    )

    # Register delete_news route
    app_instance.add_url_rule(
        "/delete_news/<int:id>",
        "delete_news",
        login_required(delete_news),
        methods=["POST"],
    )

    # Register delete_own_account route
    app_instance.add_url_rule(
        "/delete_own_account",
        "delete_own_account",
        login_required(delete_own_account),
        methods=["POST"],
    )
