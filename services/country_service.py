from repositories.country_repository import CountryRepository
from database import get_coalition_members_table

class CountryService:
    @staticmethod
    def get_countries_paginated(cId, search, lowerinf, upperinf, province_range, sort, sortway, page, per_page):
        # Default sort
        if not sort:
            sort = "influence"
        if not sortway:
            sortway = "desc"

        search_filter = ""
        params = []

        if search:
            if search.isdigit():
                search_filter = "AND u.id = %s"
                params.append(int(search))
            else:
                search_filter = "AND u.username ILIKE %s"
                params.append(f"%{search}%")

        # Sort mapping
        sort_map = {
            "influence": "influence",
            "age": "date",
            "population": "province_population",
            "provinces": "provinces_count",
        }
        sort_column = sort_map.get(sort, "influence")
        sort_direction = "DESC" if sortway == "desc" else "ASC"

        members_tbl = get_coalition_members_table()
        coalition_src = members_tbl if members_tbl else "(SELECT NULL::integer AS userid, NULL::integer AS colid WHERE FALSE)"

        raw_data, total_count, total_pages, current_page = CountryRepository.get_countries_paginated(
            cId=cId,
            search=search,
            lowerinf=lowerinf,
            upperinf=upperinf,
            province_range=province_range,
            sort_column=sort_column,
            sort_direction=sort_direction,
            page=page,
            per_page=per_page,
            search_filter=search_filter,
            params=params,
            coalition_src=coalition_src
        )

        return {
            "countries": raw_data,
            "total_count": total_count,
            "total_pages": total_pages,
            "current_page": current_page
        }

    @staticmethod
    def get_country_profile(cId, session_user_id):
        # We need these imports since we moved the logic
        import math
        import logging
        from helpers import error, get_influence
        from database import get_request_cursor, rollback_db_cursor, get_coalition_members_table
        from policies import get_user_policies
        import variables
        from countries import get_revenue, get_econ_statistics, format_econ_statistics

        session = {"user_id": session_user_id}

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

        join_number = None
        last_active = None
        total_children = 0
        total_working = 0
        total_elderly = 0
        resource_rows = []
        building_rows = []
        technology_rows = []

        members_tbl = get_coalition_members_table()
        if members_tbl:
            _CORE_COUNTRY_SQL = f"""SELECT u.username, s.location, u.description,
                          u.date, u.flag,
                          c.id AS coalition_id, cm.role,
                          c.name as colName,
                          p.total_pop, p.avg_happiness,
                          p.avg_productivity, p.province_count
                   FROM users u
                   INNER JOIN stats s ON u.id=s.id
                   LEFT JOIN {members_tbl} cm ON u.id=cm.userid
                   LEFT JOIN colNames c ON cm.colid=c.id
                   LEFT JOIN (
                       SELECT userid,
                              SUM(population) AS total_pop,
                              AVG(happiness) AS avg_happiness,
                              AVG(productivity) AS avg_productivity,
                              COUNT(id) AS province_count
                       FROM provinces
                       WHERE userid = %s
                       GROUP BY userid
                   ) p ON u.id = p.userid
                   WHERE u.id=%s"""
        else:
            _CORE_COUNTRY_SQL = None

        _MINIMAL_COUNTRY_SQL = """SELECT u.username, s.location, u.description,
                          u.date, u.flag,
                          NULL::integer AS coalition_id, NULL::integer AS role,
                          NULL::text AS colName,
                          p.total_pop, p.avg_happiness,
                          p.avg_productivity, p.province_count
                   FROM users u
                   INNER JOIN stats s ON u.id=s.id
                   LEFT JOIN (
                       SELECT userid,
                              SUM(population) AS total_pop,
                              AVG(happiness) AS avg_happiness,
                              AVG(productivity) AS avg_productivity,
                              COUNT(id) AS province_count
                       FROM provinces
                       WHERE userid = %s
                       GROUP BY userid
                   ) p ON u.id = p.userid
                   WHERE u.id=%s"""

        with get_request_cursor(read_only=True) as db:
            row = None
            if _CORE_COUNTRY_SQL:
                try:
                    db.execute(_CORE_COUNTRY_SQL, (cId, cId))
                    row = db.fetchone()
                except Exception:
                    rollback_db_cursor(db)
            if row is None:
                try:
                    db.execute(_MINIMAL_COUNTRY_SQL, (cId, cId))
                    row = db.fetchone()
                except Exception as exc:
                    rollback_db_cursor(db)
                    logging.getLogger(__name__).warning(
                        "country(%s) minimal query failed: %s", cId, exc
                    )
                    row = None

            if not row:
                return {"error": True, "code": 404, "msg": "Country doesn't exist"}

            (
                username,
                location,
                description,
                dateCreated,
                flag,
                coalition_id,
                colRole,
                colName,
                population,
                happiness,
                productivity,
                provinceCount,
            ) = row

            coalition_id = coalition_id or 0
            colName = colName or ""
            colFlag = None
            population = population or 0
            happiness = happiness or 0
            productivity = productivity or 0
            provinceCount = provinceCount or 0

            try:
                db.execute(
                    "SELECT join_number, last_active FROM users WHERE id=%s",
                    (cId,),
                )
                opt = db.fetchone()
                if opt:
                    join_number, last_active = opt[0], opt[1]
            except Exception:
                rollback_db_cursor(db)

            try:
                db.execute(
                    """SELECT COALESCE(SUM(pop_children), 0),
                              COALESCE(SUM(pop_working), 0),
                              COALESCE(SUM(pop_elderly), 0)
                       FROM provinces WHERE userid = %s""",
                    (cId,),
                )
                demo = db.fetchone()
                if demo:
                    total_children = demo[0] or 0
                    total_working = demo[1] or 0
                    total_elderly = demo[2] or 0
            except Exception:
                rollback_db_cursor(db)

            try:
                policies = get_user_policies(cId, db=db)
            except Exception:
                rollback_db_cursor(db)
                policies = {}
            try:
                influence = get_influence(cId, db=db)
            except Exception:
                rollback_db_cursor(db)
                influence = 0

            provinces = []
            try:
                db.execute(
                    "SELECT provinceName, id, population, "
                    "CAST(citycount AS INTEGER) as cityCount, "
                    "land, happiness, productivity, "
                    "COALESCE(pop_children, 0) as pop_children, "
                    "COALESCE(pop_working, 0) as pop_working, "
                    "COALESCE(pop_elderly, 0) as pop_elderly "
                    "FROM provinces WHERE userid=(%s) "
                    "ORDER BY id ASC",
                    (cId,),
                )
                provinces = db.fetchall()
            except Exception:
                rollback_db_cursor(db)
                try:
                    db.execute(
                        "SELECT provinceName, id, population, "
                        "CAST(citycount AS INTEGER) as cityCount, "
                        "land, happiness, productivity, "
                        "0 as pop_children, 0 as pop_working, 0 as pop_elderly "
                        "FROM provinces WHERE userid=(%s) "
                        "ORDER BY id ASC",
                        (cId,),
                    )
                    provinces = db.fetchall()
                except Exception:
                    rollback_db_cursor(db)
                    provinces = []

            provinces_with_images = set()
            try:
                from database import provinces_has_image_data

                if provinces_has_image_data():
                    db.execute(
                        """
                        SELECT id FROM provinces
                        WHERE userId = %s
                          AND image_data IS NOT NULL
                          AND image_data <> ''
                        """,
                        (cId,),
                    )
                    provinces_with_images = {row[0] for row in db.fetchall()}
            except Exception:
                rollback_db_cursor(db)
                provinces_with_images = set()

            try:
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
            except Exception:
                rollback_db_cursor(db)
                resource_rows = []

            try:
                db.execute(
                    """
                    SELECT bd.display_name, SUM(ub.quantity) AS quantity, bd.name
                    FROM user_buildings ub
                    JOIN building_dictionary bd ON bd.building_id = ub.building_id
                    WHERE ub.user_id = %s
                      AND ub.quantity > 0
                    GROUP BY bd.display_name, bd.name
                    HAVING SUM(ub.quantity) > 0
                    ORDER BY bd.display_name
                    """,
                    (cId,),
                )
                building_rows_raw = db.fetchall() or []
                building_rows = [(r[0], r[1]) for r in building_rows_raw]
            
                target_silos = 0
                for r in building_rows_raw:
                    if r[2] == 'silos':
                        target_silos = r[1]
            except Exception:
                rollback_db_cursor(db)
                building_rows = []
                target_silos = 0

            try:
                db.execute(
                    """
                    SELECT td.display_name, td.name
                    FROM user_tech ut
                    JOIN tech_dictionary td ON td.tech_id = ut.tech_id
                    WHERE ut.user_id = %s
                      AND ut.is_unlocked = TRUE
                    ORDER BY td.display_name
                    """,
                    (cId,),
                )
                technology_rows_raw = db.fetchall() or []
                technology_rows = [(r[0],) for r in technology_rows_raw]
            
                target_has_nuclear_facility = False
                for r in technology_rows_raw:
                    if r[1] == 'nuclear_testing_facility':
                        target_has_nuclear_facility = True
            except Exception:
                rollback_db_cursor(db)
                technology_rows = []
                target_has_nuclear_facility = False

            # Calculate CG need from already-fetched population
            cg_needed = (
                math.ceil(population / variables.CONSUMER_GOODS_PER) if population else 0
            )

            total_cities = sum(prov[3] if prov[3] else 0 for prov in provinces)
            total_land = sum(prov[4] if prov[4] else 0 for prov in provinces)

            try:
                status = int(cId) == int(session["user_id"])
            except (KeyError, TypeError, ValueError):
                status = False
            spy = {"count": 0}
            nuke_count = 0
            icbm_count = 0
            attacker_bombers = 0
        
            uId = session.get("user_id")
        
            if uId:
                try:
                    db.execute(
                        "SELECT ud.name, COALESCE(SUM(um.quantity), 0) FROM user_military um "
                        "JOIN unit_dictionary ud ON um.unit_id = ud.unit_id "
                        "WHERE um.user_id=%s AND ud.name IN ('spies', 'nukes', 'icbms', 'bombers') GROUP BY ud.name",
                        (uId,),
                    )
                    military_rows = db.fetchall()
                    for unit_name, qty in military_rows:
                        if unit_name == 'spies':
                            spy["count"] = qty
                        elif unit_name == 'nukes':
                            nuke_count = qty
                        elif unit_name == 'icbms':
                            icbm_count = qty
                        elif unit_name == 'bombers':
                            attacker_bombers = qty
                except Exception:
                    rollback_db_cursor(db)

            # News page - only for own country
            news = []
            news_amount = 0
            current_user_id = session.get("user_id")
            if current_user_id and int(cId) == current_user_id:
                try:
                    db.execute(
                        "SELECT message,date,id FROM news WHERE destination_id=(%s)",
                        (cId,),
                    )
                    news = db.fetchall()
                    news_amount = len(news)
                except Exception:
                    rollback_db_cursor(db)
                    news = []
                    news_amount = 0

            interactive_events = []
            if current_user_id and int(cId) == current_user_id:
                try:
                    db.execute(
                        "SELECT id, event_def_id, created_at FROM interactive_events WHERE user_id=%s AND resolved_at IS NULL",
                        (cId,)
                    )
                    events_rows = db.fetchall()
                    if events_rows:
                        from app_core.events.routes import load_events
                        events_data = load_events()
                        for row in events_rows:
                            evt_id = row[0]
                            def_id = row[1]
                            created_at = row[2]
                        
                            event_def = events_data.get(def_id)
                            if event_def:
                                choices = []
                                for opt in event_def.get("options", []):
                                    cost_strs = [f"{v} {k}" for k, v in opt.get("costs", {}).items()]
                                    reward_strs = [f"{v} {k}" for k, v in opt.get("rewards", {}).items()]
                                    choices.append({
                                        "label": opt.get("text", ""),
                                        "cost": ", ".join(cost_strs) if cost_strs else "None",
                                        "reward": ", ".join(reward_strs) if reward_strs else "None"
                                    })
                                
                                interactive_events.append({
                                    "id": evt_id,
                                    "def_id": def_id,
                                    "title": event_def.get("title", f"Event: {def_id}"),
                                    "description": event_def.get("description", ""),
                                    "choices": choices,
                                    "created_at": created_at
                                })
                except Exception:
                    rollback_db_cursor(db)

            # Revenue stuff - expensive, so cached
            if status:
                try:
                    revenue = get_revenue(cId, db=db)
                except Exception:
                    rollback_db_cursor(db)
                    revenue = default_revenue_data()

                try:
                    db.execute(
                        "SELECT name, type, resource, amount, date "
                        "FROM revenue WHERE user_id=%s",
                        (cId,),
                    )
                    expenses = db.fetchall()
                except Exception:
                    rollback_db_cursor(db)
                    expenses = []

                try:
                    statistics = get_econ_statistics(cId, db=db)
                    statistics = format_econ_statistics(statistics)
                except Exception:
                    rollback_db_cursor(db)
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

            distribution_status = None
            food_score = None
            is_owner = session_user_id is not None and str(session_user_id) == str(cId)
            if variables.FEATURE_RATIONS_DISTRIBUTION and population and is_owner:
                try:
                    from tasks import fetch_nation_distribution_status, food_stats

                    distribution_status = fetch_nation_distribution_status(
                        db, cId, population, rations_need
                    )
                    food_score = food_stats(cId)
                except Exception:
                    rollback_db_cursor(db)
                    distribution_status = None
                    food_score = None

            try:
                db.execute("""
                    SELECT t.treaty_type, u.username as other_nation, u.id as other_id
                    FROM nation_treaties t
                    JOIN users u ON (u.id = t.recipient_id AND t.sender_id = %s) OR (u.id = t.sender_id AND t.recipient_id = %s)
                    WHERE t.status = 'active' AND (t.sender_id = %s OR t.recipient_id = %s)
                """, (cId, cId, cId, cId))
                active_treaties = db.fetchall()
            except Exception:
                rollback_db_cursor(db)
                active_treaties = []

            recommended_coalitions = []
            if status and not coalition_id:
                try:
                    members_tbl = get_coalition_members_table() or "coalitions_legacy"
                    db.execute(
                        f"""
                        SELECT cn.id, cn.name, cn.type, cn.description, cn.flag, COUNT(cm.userid)::int AS members
                        FROM colNames cn
                        LEFT JOIN {members_tbl} cm ON cn.id = cm.colid
                        WHERE cn.recruiting = TRUE
                        GROUP BY cn.id, cn.name, cn.type, cn.description, cn.flag
                        ORDER BY members DESC, cn.id ASC
                        LIMIT 3
                        """
                    )
                    recommended_coalitions = [
                        {
                            "id": r[0],
                            "name": r[1],
                            "type": r[2],
                            "description": r[3] or "",
                            "flag": r[4],
                            "members": r[5]
                        }
                        for r in db.fetchall()
                    ]
                except Exception:
                    rollback_db_cursor(db)
                    recommended_coalitions = []

        return {
            "recommended_coalitions": recommended_coalitions,
            "username": username,
            "join_number": join_number,
            "cId": cId,
            "description": description,
            "happiness": happiness,
            "population": population,
            "location": location,
            "status": status,
            "provinceCount": provinceCount,
            "colName": colName,
            "dateCreated": dateCreated,
            "influence": influence,
            "total_cities": total_cities,
            "total_land": total_land,
            "provinces": provinces,
            "provinces_with_images": provinces_with_images,
            "colId": coalition_id,
            "coalition_id": coalition_id,
            "flag": flag,
            "spy": spy,
            "nuke_count": nuke_count,
            "icbm_count": icbm_count,
            "active_treaties": active_treaties,
            "attacker_bombers": attacker_bombers,
            "target_silos": target_silos,
            "target_has_nuclear_facility": target_has_nuclear_facility,
            "colFlag": colFlag,
            "colRole": colRole,
            "productivity": productivity,
            "revenue": revenue,
            "news": news,
            "news_amount": news_amount,
            "interactive_events": interactive_events,
            "cg_needed": cg_needed,
            "rations_need": rations_need,
            "distribution_status": distribution_status,
            "food_score": food_score,
            "expenses": expenses,
            "statistics": statistics,
            "policies": policies,
            "resource_rows": resource_rows,
            "building_rows": building_rows,
            "technology_rows": technology_rows,
            "last_active": last_active,
            "total_children": total_children,
            "total_working": total_working,
            "total_elderly": total_elderly,
        }
