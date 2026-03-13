from flask import request, render_template, session, redirect
from helpers import login_required
from helpers import get_influence, error
from database import invalidate_view_cache
import os
import variables
from dotenv import load_dotenv
from collections import defaultdict
from policies import get_user_policies
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
        total = {name: 0 for name in variables.NEW_INFRA.keys()}
        dbdict.execute(
            """
            SELECT bd.name, COALESCE(SUM(ub.quantity), 0) AS total_quantity
            FROM user_buildings ub
            JOIN building_dictionary bd ON bd.building_id = ub.building_id
            WHERE ub.user_id = %s
            GROUP BY bd.name
            """,
            (cId,),
        )
        for row in dbdict.fetchall() or []:
            bname = row.get("name")
            qty = row.get("total_quantity") or 0
            if bname:
                total[bname] = qty

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
    from database import query_cache

    # Check cache first - expensive calculation
    cache_key = f"revenue_{cId}"
    cached = query_cache.get(cache_key)
    if cached is not None:
        return cached

    with get_db_cursor(read_only=True) as db:
        # Prefetch province ids, land, productivity, and population
        db.execute(
            "SELECT id, land, productivity, population FROM provinces WHERE userid=%s",
            (cId,),
        )
        province_rows = db.fetchall()
        provinces = [row[0] for row in province_rows]
        land_by_id = {row[0]: row[1] for row in province_rows}
        prod_by_id = {row[0]: row[2] for row in province_rows}

        revenue = {"gross": {}, "gross_theoretical": {}, "net": {}}

        infra = variables.NEW_INFRA
        resources = list(variables.RESOURCES)
        resources.extend(["money", "energy"])
        for resource in resources:
            revenue["gross"][resource] = 0
            revenue["gross_theoretical"][resource] = 0
            revenue["net"][resource] = 0

        # Batch fetch all building data PER PROVINCE
        proinfra_by_id = {}
        if provinces:
            province_ids = list(provinces)
            db.execute(
                """
                SELECT ub.province_id, bd.name, ub.quantity
                FROM user_buildings ub
                JOIN building_dictionary bd ON bd.building_id = ub.building_id
                WHERE ub.user_id = %s AND ub.province_id = ANY(%s)
                """,
                (cId, province_ids),
            )
            for row in db.fetchall():
                prov_id, building_name, quantity = row
                if prov_id not in proinfra_by_id:
                    proinfra_by_id[prov_id] = {}
                proinfra_by_id[prov_id][building_name] = quantity or 0

        # Fetch gold, rations, and CG in a single combined query
        db.execute(
            """
            SELECT
                COALESCE(s.gold, 0) AS gold,
                COALESCE(r.quantity, 0) AS rations,
                COALESCE(cg.quantity, 0) AS consumer_goods
            FROM stats s
            LEFT JOIN (
                SELECT ue.quantity FROM user_economy ue
                JOIN resource_dictionary rd ON rd.resource_id = ue.resource_id
                WHERE ue.user_id = %s AND rd.name = 'rations'
            ) r ON TRUE
            LEFT JOIN (
                SELECT ue.quantity FROM user_economy ue
                JOIN resource_dictionary rd ON rd.resource_id = ue.resource_id
                WHERE ue.user_id = %s AND rd.name = 'consumer_goods'
            ) cg ON TRUE
            WHERE s.id = %s
            """,
            (cId, cId, cId),
        )
        econ_row = db.fetchone()
        current_money = econ_row[0] if econ_row else 0
        current_rations = econ_row[1] if econ_row else 0
        consumer_goods = int(econ_row[2]) if econ_row else 0

        # Simulated funds used while computing `net`; do not mutate DB
        simulated_funds = current_money

        for province in provinces:
            buildings = proinfra_by_id.get(province)
            if buildings is None:
                buildings = {}

            for building, build_count in buildings.items():
                if building == "id":
                    continue
                if build_count is None or build_count == 0:
                    continue
                if building not in infra:
                    continue

                operating_costs = infra[building]["money"] * build_count

                # Add to gross/net resource production only if this building would
                # actually operate given the player's money. We keep `gross` and
                # `gross_theoretical` as unconditional projections, but `net`
                # reflects a simple money-constrained simulation similar to the
                # actual task runner so UI `net` is consistent with what will
                # actually happen.
                will_operate = simulated_funds >= operating_costs

                if will_operate:
                    simulated_funds -= operating_costs
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

                    # Record the theoretical and gross projections
                    revenue["gross_theoretical"][resource] += theoretical_total
                    revenue["gross"][resource] += adjusted_total

                    # Only add to `net` if the building will operate
                    if will_operate:
                        revenue["net"][resource] += adjusted_total

                minus = infra[building].get("minus", {})
                for resource, amount in minus.items():
                    total = build_count * amount
                    # Only subtract upkeep from net if building operates
                    if will_operate:
                        revenue["net"][resource] -= total

        # Fetch policies for tax calculation
        try:
            db.execute("SELECT education FROM policies WHERE user_id=%s", (cId,))
            policies_row = db.fetchone()
            policies = policies_row[0] if policies_row else []
        except Exception:
            policies = []

        # Reuse already-fetched province data for tax income calculation
        # province_rows is (id, land, productivity, population)
        ti_provinces = [(row[3], row[1]) for row in province_rows]  # (pop, land)

        ti_money = 0
        if ti_provinces:
            for population, land in ti_provinces:
                land_multiplier = (land - 1) * variables.DEFAULT_LAND_TAX_MULTIPLIER
                if land_multiplier > 1:
                    land_multiplier = 1
                base_multiplier = variables.DEFAULT_TAX_INCOME
                if policies and 1 in policies:
                    base_multiplier *= 1.01
                if policies and 6 in policies:
                    base_multiplier *= 0.98
                if policies and 4 in policies:
                    base_multiplier *= 0.98
                multiplier = base_multiplier + (base_multiplier * land_multiplier)
                ti_money += multiplier * population

            total_pop_ti = sum(p for p, _ in ti_provinces)
            max_cg = math.ceil(total_pop_ti / variables.CONSUMER_GOODS_PER)
            if consumer_goods != 0 and max_cg != 0:
                if max_cg <= consumer_goods:
                    ti_money *= variables.CONSUMER_GOODS_TAX_MULTIPLIER
                else:
                    cg_multiplier = consumer_goods / max_cg
                    ti_money *= 1 + (0.5 * cg_multiplier)

        ti_money = math.floor(ti_money)

        # Updates money
        revenue["gross"]["money"] += ti_money
        revenue["net"]["money"] += ti_money

        # Reuse already-fetched data for CG need calculation
        total_population = sum(row[3] or 0 for row in province_rows)
        citizen_cg_need = math.ceil(total_population / variables.CONSUMER_GOODS_PER)

        # Net consumer goods = gross production - citizen need
        # (gross already includes production from buildings that would operate)
        revenue["net"]["consumer_goods"] = (
            revenue["gross"]["consumer_goods"] - citizen_cg_need
        )

        prod_rations = revenue["gross"]["rations"]
        # Calculate next turn rations inline using already-fetched data
        current_rations_for_calc = current_rations + prod_rations
        # Calculate consumption from already-fetched province_rows
        total_rations_needed = 0
        for row in province_rows:
            province_pop = row[3] if row[3] else 0  # index 3 is population
            province_consumption = province_pop // variables.RATIONS_PER
            if province_consumption < 1:
                province_consumption = 1
            total_rations_needed += province_consumption
        if total_rations_needed < 1:
            total_rations_needed = 1
        new_rations = max(0, current_rations_for_calc - total_rations_needed)
        revenue["net"]["rations"] = new_rations - current_rations

        # Filter to only show resources with positive gross production
        # or non-zero net (for special cases like rations)
        # Keep `gross_theoretical` present so templates can always access it
        filtered_revenue = {
            "gross": revenue["gross"],
            "gross_theoretical": revenue["gross_theoretical"],
            "net": revenue["net"],
        }

        # Cache the result for 60 seconds (revenue doesn't change often)
        query_cache.set(cache_key, filtered_revenue, ttl_seconds=60)

        return filtered_revenue


def next_turn_rations(cId, prod_rations):
    """Calculate next turn rations after consumption."""
    with get_db_cursor() as db:
        # Get current rations (normalized economy)
        db.execute(
            """
            SELECT ue.quantity
            FROM user_economy ue
            JOIN resource_dictionary rd ON rd.resource_id = ue.resource_id
            WHERE ue.user_id=%s AND rd.name='rations'
            """,
            (cId,),
        )
        rr = db.fetchone()
        current_rations = (rr[0] if rr and rr[0] is not None else 0) + prod_rations

        # Get population per province to calculate consumption correctly
        # (each province consumes at minimum 1 ration, matching population_growth task)
        db.execute(
            "SELECT population FROM provinces WHERE userid=%s",
            (cId,),
        )
        provinces = db.fetchall()

        # Calculate total consumption matching the population_growth task logic
        total_rations_needed = 0
        for (pop,) in provinces:
            province_pop = pop if pop else 0
            province_consumption = province_pop // variables.RATIONS_PER
            if province_consumption < 1:
                province_consumption = 1
            total_rations_needed += province_consumption

        # If no provinces, still need minimum 1
        if total_rations_needed < 1:
            total_rations_needed = 1

        # Calculate remaining rations after consumption
        remaining_rations = current_rations - total_rations_needed
        if remaining_rations < 0:
            remaining_rations = 0

        return int(remaining_rations)


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
    with get_db_cursor() as db:
        db.execute("SELECT SUM(population) FROM provinces WHERE userid=%s", (user_id,))
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
    """
    PERFORMANCE OPTIMIZED: Reduced from 10+ separate queries to 4 combined queries.
    Uses caching for expensive calculations (revenue, statistics).
    """

    def default_revenue_data():
        base_resources = [
            "rations",
            "oil",
            "coal",
            "uranium",
            "bauxite",
            "iron",
            "lead",
            "copper",
            "lumber",
            "components",
            "steel",
            "consumer_goods",
            "aluminium",
            "gasoline",
            "ammunition",
            "money",
            "energy",
        ]
        gross = {r: 0 for r in base_resources}
        net = {r: 0 for r in base_resources}
        return {"gross": gross, "net": net, "gross_theoretical": gross.copy()}

    def default_statistics_data():
        return {
            "electricity": 0,
            "retail": 0,
            "public_works": 0,
            "military": 0,
            "industry": 0,
            "processing": 0,
        }

    with get_db_cursor(read_only=True) as db:
        # OPTIMIZED: Combined user+stats+coalition+province aggregates in ONE query
        db.execute(
            """SELECT u.username, s.location, u.description,
                      u.date, u.flag, u.join_number,
                      c.id AS coalition_id, cm.role,
                      c.name as colName,
                      p.total_pop, p.avg_happiness,
                      p.avg_productivity, p.province_count,
                      u.last_active,
                      p.total_children, p.total_working, p.total_elderly
               FROM users u
               INNER JOIN stats s ON u.id=s.id
               LEFT JOIN coalitions_legacy cm ON u.id=cm.userid
               LEFT JOIN colNames c ON cm.colid=c.id
               LEFT JOIN (
                   SELECT userid,
                          SUM(population) AS total_pop,
                          AVG(happiness) AS avg_happiness,
                          AVG(productivity) AS avg_productivity,
                          COUNT(id) AS province_count,
                          SUM(COALESCE(pop_children, 0)) AS total_children,
                          SUM(COALESCE(pop_working, 0)) AS total_working,
                          SUM(COALESCE(pop_elderly, 0)) AS total_elderly
                   FROM provinces
                   WHERE userid = %s
                   GROUP BY userid
               ) p ON u.id = p.userid
               WHERE u.id=%s""",
            (cId, cId),
        )
        row = db.fetchone()
        if not row:
            return error(404, "Country doesn't exist")

        (
            username,
            location,
            description,
            dateCreated,
            flag,
            join_number,
            coalition_id,
            colRole,
            colName,
            population,
            happiness,
            productivity,
            provinceCount,
            last_active,
            total_children,
            total_working,
            total_elderly,
        ) = row

        # Set defaults for None values
        coalition_id = coalition_id or 0
        colName = colName or ""
        colFlag = None
        population = population or 0
        happiness = happiness or 0
        productivity = productivity or 0
        provinceCount = provinceCount or 0
        total_children = total_children or 0
        total_working = total_working or 0
        total_elderly = total_elderly or 0

        # Get policies and influence (these are already cached)
        policies = get_user_policies(cId)
        influence = get_influence(cId)

        # Get provinces list with demographics
        db.execute(
            "SELECT provinceName, id, population, "
            "CAST(cityCount AS INTEGER) as cityCount, "
            "land, happiness, productivity, "
            "COALESCE(pop_children, 0) as pop_children, "
            "COALESCE(pop_working, 0) as pop_working, "
            "COALESCE(pop_elderly, 0) as pop_elderly "
            "FROM provinces WHERE userid=(%s) "
            "ORDER BY id ASC",
            (cId,),
        )
        provinces = db.fetchall()

        # Normalized resource display
        db.execute(
            """
            SELECT rd.display_name, COALESCE(ue.quantity, 0) AS quantity
            FROM resource_dictionary rd
            LEFT JOIN user_economy ue
              ON ue.resource_id = rd.resource_id
             AND ue.user_id = %s
            ORDER BY rd.resource_id
            """,
            (cId,),
        )
        resource_rows = db.fetchall() or []

        # Normalized buildings display (national totals across all provinces)
        db.execute(
            """
            SELECT bd.display_name, SUM(ub.quantity) AS quantity
            FROM user_buildings ub
            JOIN building_dictionary bd ON bd.building_id = ub.building_id
            WHERE ub.user_id = %s
              AND ub.quantity > 0
            GROUP BY bd.display_name
            HAVING SUM(ub.quantity) > 0
            ORDER BY bd.display_name
            """,
            (cId,),
        )
        building_rows = db.fetchall() or []

        # Normalized technologies display (unlocked only)
        db.execute(
            """
            SELECT td.display_name
            FROM user_tech ut
            JOIN tech_dictionary td ON td.tech_id = ut.tech_id
            WHERE ut.user_id = %s
              AND ut.is_unlocked = TRUE
            ORDER BY td.display_name
            """,
            (cId,),
        )
        technology_rows = db.fetchall() or []

        # Calculate CG need from already-fetched population
        cg_needed = (
            math.ceil(population / variables.CONSUMER_GOODS_PER) if population else 0
        )

        try:
            status = cId == str(session["user_id"])
        except (KeyError, TypeError):
            status = False

        spy = {}
        uId = session.get("user_id")
        if uId:
            db.execute(
                """
                SELECT COALESCE(SUM(um.quantity), 0)
                FROM user_military um
                JOIN unit_dictionary ud ON ud.unit_id = um.unit_id
                WHERE um.user_id = %s
                  AND ud.name = 'spies'
                """,
                (uId,),
            )
            spy_row = db.fetchone()
            spy["count"] = spy_row[0] if spy_row else 0
        else:
            spy["count"] = 0

        # News page - only for own country
        news = []
        news_amount = 0
        current_user_id = session.get("user_id")
        if current_user_id and int(cId) == current_user_id:
            db.execute(
                "SELECT message,date,id FROM news WHERE destination_id=(%s)", (cId,)
            )
            news = db.fetchall()
            news_amount = len(news)

        # Revenue stuff - expensive, so cached
        if status:
            try:
                revenue = get_revenue(cId)
            except Exception:
                revenue = default_revenue_data()

            db.execute(
                "SELECT name, type, resource, amount, date "
                "FROM revenue WHERE user_id=%s",
                (cId,),
            )
            expenses = db.fetchall()

            try:
                statistics = get_econ_statistics(cId)
                statistics = format_econ_statistics(statistics)
            except Exception:
                statistics = default_statistics_data()

            for key, value in default_statistics_data().items():
                statistics.setdefault(key, value)
        else:
            revenue = default_revenue_data()
            expenses = []
            statistics = default_statistics_data()

        # Calculate rations need from already-fetched provinces data
        # Each province needs at least 1 ration, or population // RATIONS_PER
        rations_need = 0
        for prov in provinces:
            pop = prov[2] if prov[2] else 0  # index 2 is population
            consumption = pop // variables.RATIONS_PER
            if consumption < 1:
                consumption = 1
            rations_need += consumption
        if rations_need < 1:
            rations_need = 1

    return render_template(
        "country.html",
        username=username,
        join_number=join_number,
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
        colId=coalition_id,
        coalition_id=coalition_id,
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
        resource_rows=resource_rows,
        building_rows=building_rows,
        technology_rows=technology_rows,
        last_active=last_active,
        total_children=total_children,
        total_working=total_working,
        total_elderly=total_elderly,
    )


def countries():
    cId = session["user_id"]

    # Parse and coerce query params
    search = request.values.get("search", "").strip()
    lowerinf = request.values.get("lowerinf", type=float)
    upperinf = request.values.get("upperinf", type=float)
    province_range = request.values.get("province_range", default=0, type=int)
    sort = request.values.get("sort")
    sortway = request.values.get("sortway")
    page = request.values.get("page", default=1, type=int)
    # Allow users to choose page size: 50, 100, or 150
    per_page = request.values.get("per_page", default=50, type=int)
    if per_page not in [50, 100, 150]:
        per_page = 50

    if sort == "war_range":
        target = target_data(cId)
        lowerinf = float(target.get("lower", 0))
        upperinf = float(target.get("upper", 0))
        province_range = int(target.get("province_range", 0))

    # Default sort
    if not sort:
        sort = "influence"
        sortway = "desc"
    if not sortway:
        sortway = "desc"

    search_filter = ""
    params = []

    if search:
        if search.isdigit():
            search_filter = "AND u.id = %s"
            params.append(int(search))
        else:
            search_filter = "AND LOWER(u.username) LIKE LOWER(%s)"
            params.append(f"%{search}%")

    # Sort mapping is constrained to safe SQL snippets only.
    sort_map = {
        "influence": "influence",
        "age": "date",
        "population": "province_population",
        "provinces": "provinces_count",
    }
    sort_column = sort_map.get(sort, "influence")
    sort_direction = "DESC" if sortway == "desc" else "ASC"

    with get_db_cursor(read_only=True) as db:
        filter_sql = f"""
            WITH country_rows AS (
                SELECT
                    u.id,
                    u.username,
                    u.date,
                    u.flag,
                    COALESCE(p.province_population, 0) AS province_population,
                    cm.colid,
                    c.name,
                    COALESCE(p.provinces_count, 0) AS provinces_count,
                    u.join_number,
                    ROUND(
                        COALESCE(p.provinces_count, 0) * 300
                        + COALESCE(m.soldiers, 0) * 0.02
                        + COALESCE(m.artillery, 0) * 1.6
                        + COALESCE(m.tanks, 0) * 0.8
                        + COALESCE(m.fighters, 0) * 3.5
                        + COALESCE(m.bombers, 0) * 2.5
                        + COALESCE(m.apaches, 0) * 3.2
                        + COALESCE(m.submarines, 0) * 4.5
                        + COALESCE(m.destroyers, 0) * 3
                        + COALESCE(m.cruisers, 0) * 5.5
                        + COALESCE(m.icbms, 0) * 250
                        + COALESCE(m.nukes, 0) * 500
                        + COALESCE(m.spies, 0) * 25
                        + COALESCE(p.city_count, 0) * 10
                        + COALESCE(p.total_land, 0) * 10
                        + COALESCE(r.total_resources, 0) * 0.001
                        + COALESCE(s.gold, 0) * 0.00001
                    )::bigint AS influence,
                    COALESCE(EXTRACT(EPOCH FROM u.date)::bigint, 0) AS unix
                FROM users u
                LEFT JOIN stats s ON s.id = u.id
                LEFT JOIN (
                    SELECT
                        userId AS user_id,
                        COUNT(id) AS provinces_count,
                        COALESCE(SUM(population), 0) AS province_population,
                        COALESCE(SUM(cityCount), 0) AS city_count,
                        COALESCE(SUM(land), 0) AS total_land
                    FROM provinces
                    GROUP BY userId
                ) p ON p.user_id = u.id
                LEFT JOIN (
                    SELECT
                        um.user_id,
                        SUM(
                            CASE WHEN ud.name='soldiers' THEN um.quantity ELSE 0 END
                        ) AS soldiers,
                        SUM(
                            CASE WHEN ud.name='artillery' THEN um.quantity ELSE 0 END
                        ) AS artillery,
                        SUM(
                            CASE WHEN ud.name='tanks' THEN um.quantity ELSE 0 END
                        ) AS tanks,
                        SUM(
                            CASE WHEN ud.name='fighters' THEN um.quantity ELSE 0 END
                        ) AS fighters,
                        SUM(
                            CASE WHEN ud.name='bombers' THEN um.quantity ELSE 0 END
                        ) AS bombers,
                        SUM(
                            CASE WHEN ud.name='apaches' THEN um.quantity ELSE 0 END
                        ) AS apaches,
                        SUM(
                            CASE
                                WHEN ud.name='submarines' THEN um.quantity
                                ELSE 0
                            END
                        ) AS submarines,
                        SUM(
                            CASE
                                WHEN ud.name='destroyers' THEN um.quantity
                                ELSE 0
                            END
                        ) AS destroyers,
                        SUM(
                            CASE WHEN ud.name='cruisers' THEN um.quantity ELSE 0 END
                        ) AS cruisers,
                        SUM(
                            CASE WHEN ud.name='icbms' THEN um.quantity ELSE 0 END
                        ) AS icbms,
                        SUM(
                            CASE WHEN ud.name='nukes' THEN um.quantity ELSE 0 END
                        ) AS nukes,
                        SUM(
                            CASE WHEN ud.name='spies' THEN um.quantity ELSE 0 END
                        ) AS spies
                    FROM user_military um
                    JOIN unit_dictionary ud ON ud.unit_id = um.unit_id
                    GROUP BY um.user_id
                ) m ON m.user_id = u.id
                LEFT JOIN (
                    SELECT user_id, COALESCE(SUM(quantity), 0) AS total_resources
                    FROM user_economy
                    GROUP BY user_id
                ) r ON r.user_id = u.id
                LEFT JOIN (
                    SELECT userid, MIN(colid) AS colid
                    FROM coalitions_legacy
                    GROUP BY userid
                ) cm ON cm.userid = u.id
                LEFT JOIN colNames c ON c.id = cm.colid
                WHERE 1=1
                {search_filter}
            )
            SELECT *
            FROM country_rows
            WHERE provinces_count >= %s
              AND (%s IS NULL OR influence >= %s)
              AND (%s IS NULL OR influence <= %s)
        """

        filter_params = list(params)
        filter_params.extend(
            [
                province_range,
                lowerinf,
                lowerinf,
                upperinf,
                upperinf,
            ]
        )

        db.execute(
            f"SELECT COUNT(*) FROM ({filter_sql}) AS filtered", tuple(filter_params)
        )
        total_count = db.fetchone()[0] or 0

        total_pages = max(1, (total_count + per_page - 1) // per_page)
        if page < 1:
            page = 1
        if page > total_pages:
            page = total_pages
        offset = (page - 1) * per_page

        page_query = (
            f"{filter_sql} ORDER BY {sort_column} {sort_direction}, "
            "id ASC LIMIT %s OFFSET %s"
        )
        page_params = list(filter_params)
        page_params.extend([per_page, offset])
        db.execute(page_query, tuple(page_params))
        paginated_results = db.fetchall()

    return render_template(
        "countries.html",
        countries=paginated_results,
        current_user_id=cId,
        current_page=page,
        total_pages=total_pages,
        total_count=total_count,
        per_page=per_page,
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
            # Reset raw-extraction buildings when changing biome/location.
            # Legacy schema used proInfra rows keyed by province id; normalized
            # schema stores these in user_buildings keyed by user_id.
            db.execute(
                """
                UPDATE user_buildings ub
                SET quantity = 0
                FROM building_dictionary bd
                WHERE ub.building_id = bd.building_id
                  AND ub.user_id = %s
                  AND bd.name IN (
                      'pumpjacks',
                      'coal_mines',
                      'bauxite_mines',
                      'copper_mines',
                      'uranium_mines',
                      'lead_mines',
                      'iron_mines',
                      'lumber_mills'
                  )
                """,
                (cId,),
            )
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
        db.execute("DELETE FROM user_military WHERE user_id=(%s)", (cId,))
        deleted_counts["user_military"] = db.rowcount
        db.execute("DELETE FROM user_economy WHERE user_id=(%s)", (cId,))
        deleted_counts["user_economy"] = db.rowcount

        # Deletes all market things the user is associated with
        db.execute("DELETE FROM offers WHERE user_id=(%s)", (cId,))
        deleted_counts["offers"] = db.rowcount
        db.execute(
            "DELETE FROM wars WHERE defender_id=%s OR attacker_id=%s", (cId, cId)
        )
        deleted_counts["wars"] = db.rowcount

        # Deletes all the users provinces and their infrastructure
        # OPTIMIZATION: Batch delete instead of N+1 queries
        db.execute("SELECT id FROM provinces WHERE userid=%s", (cId,))
        province_ids = db.fetchall()
        if province_ids:
            ids = [p[0] for p in province_ids]
            placeholders = ",".join(["%s"] * len(ids))
            db.execute(
                f"DELETE FROM provinces WHERE id IN ({placeholders})", tuple(ids)
            )
            deleted_counts["provinces"] = db.rowcount

        # Delete user buildings (keyed by user_id, not province_id)
        db.execute("DELETE FROM user_buildings WHERE user_id=(%s)", (cId,))
        deleted_counts["user_buildings"] = db.rowcount
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
            db.execute("SELECT colid FROM coalitions_legacy WHERE userid=%s", (cId,))
            user_coalition = db.fetchone()[0]

            db.execute(
                "SELECT COUNT(userid) FROM coalitions_legacy "
                "WHERE role='leader' AND colid=%s",
                (user_coalition,),
            )
            leader_count = db.fetchone()[0]

            if leader_count != 1:
                pass
            else:
                db.execute(
                    "DELETE FROM coalitions_legacy WHERE colid=%s",
                    (user_coalition,),
                )
                db.execute("DELETE FROM colNames WHERE id=%s", (user_coalition,))
                db.execute("DELETE FROM colBanks WHERE colId=%s", (user_coalition,))
                db.execute("DELETE FROM requests WHERE colId=%s", (user_coalition,))

        db.execute("DELETE FROM coalitions_legacy WHERE userid=%s", (cId,))
        db.execute("DELETE FROM colBanksRequests WHERE reqId=%s", (cId,))

        # Clean up Economy 2.0 normalized tables
        db.execute("DELETE FROM user_tech WHERE user_id=%s", (cId,))
        deleted_counts["user_tech"] = db.rowcount
        db.execute("DELETE FROM policies WHERE user_id=%s", (cId,))
        deleted_counts["policies"] = db.rowcount
        db.execute("DELETE FROM news WHERE destination_id=%s", (cId,))
        deleted_counts["news"] = db.rowcount

        try:
            import logging

            logging.getLogger(__name__).info(
                "delete_own_account: deleted_counts=%s", deleted_counts
            )
        except Exception:
            pass

        # --- CACHE INVALIDATION ------------------------------------------------
        # Removing a nation should immediately purge any leaderboard / country
        # page HTML that might still reference the departed player. Without this
        # the /countries view (cached for 60s) can continue to serve a stale
        # copy with links pointing at the old id. Players who quickly delete and
        # re‑roll would see their new name on the leaderboard, click it, and hit
        # "Country doesn't exist".  The Discord bug report describes exactly
        # that behaviour.
        #
        # Invalidate the entire countries listing (affects all users) and clear
        # any cached individual country pages for the deleted id.  We also kick
        # the my_country cache for good measure.
        try:
            invalidate_view_cache("countries")
            invalidate_view_cache("country", page=f"/country/id={cId}")
            invalidate_view_cache("my_country", user_id=cId)
        except Exception:
            pass
        # ----------------------------------------------------------------------

    session.clear()

    return redirect("/")


def register_countries_routes(app_instance):
    """Register all routes from countries module after app initialization.

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
    # Public route - anyone can view a nation's page
    # Cache is short (30s) since users viewing their own country
    # need fresh data after edits
    app_instance.add_url_rule(
        "/country/id=<cId>",
        "country",
        cache_response(ttl_seconds=30)(country),
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
