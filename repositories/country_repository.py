from database import get_request_cursor
from psycopg2.extras import RealDictCursor

class CountryRepository:
    @staticmethod
    def get_countries_paginated(
        cId: int, 
        search: str, 
        lowerinf: float, 
        upperinf: float, 
        province_range: int, 
        sort_column: str, 
        sort_direction: str, 
        page: int, 
        per_page: int,
        search_filter: str,
        params: list,
        coalition_src: str
    ) -> tuple:
        with get_request_cursor(read_only=True) as db:
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
                        NULL::integer AS join_number,
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
                        COALESCE(EXTRACT(EPOCH FROM (CASE WHEN u.date ~ '^\\d{{4}}-\\d{{2}}-\\d{{2}}' THEN u.date ELSE '1970-01-01' END)::timestamp)::bigint, 0) AS unix
                    FROM users u
                    LEFT JOIN stats s ON s.id = u.id
                    LEFT JOIN (
                        SELECT
                            userid AS user_id,
                            COUNT(id) AS provinces_count,
                            COALESCE(SUM(population), 0) AS province_population,
                            COALESCE(SUM(citycount), 0) AS city_count,
                            COALESCE(SUM(land), 0) AS total_land
                        FROM provinces
                        GROUP BY userid
                    ) p ON p.user_id = u.id
                    LEFT JOIN (
                        SELECT
                            um.user_id,
                            SUM(CASE WHEN ud.name='soldiers' THEN um.quantity ELSE 0 END) AS soldiers,
                            SUM(CASE WHEN ud.name='artillery' THEN um.quantity ELSE 0 END) AS artillery,
                            SUM(CASE WHEN ud.name='tanks' THEN um.quantity ELSE 0 END) AS tanks,
                            SUM(CASE WHEN ud.name='fighters' THEN um.quantity ELSE 0 END) AS fighters,
                            SUM(CASE WHEN ud.name='bombers' THEN um.quantity ELSE 0 END) AS bombers,
                            SUM(CASE WHEN ud.name='apaches' THEN um.quantity ELSE 0 END) AS apaches,
                            SUM(CASE WHEN ud.name='submarines' THEN um.quantity ELSE 0 END) AS submarines,
                            SUM(CASE WHEN ud.name='destroyers' THEN um.quantity ELSE 0 END) AS destroyers,
                            SUM(CASE WHEN ud.name='cruisers' THEN um.quantity ELSE 0 END) AS cruisers,
                            SUM(CASE WHEN ud.name='icbms' THEN um.quantity ELSE 0 END) AS icbms,
                            SUM(CASE WHEN ud.name='nukes' THEN um.quantity ELSE 0 END) AS nukes,
                            SUM(CASE WHEN ud.name='spies' THEN um.quantity ELSE 0 END) AS spies
                        FROM unit_members um
                        JOIN unit_dictionary ud ON um.unit_id = ud.id
                        GROUP BY um.user_id
                    ) m ON m.user_id = u.id
                    LEFT JOIN (
                        SELECT
                            user_id,
                            COALESCE(SUM(quantity), 0) AS total_resources
                        FROM resource_members
                        GROUP BY user_id
                    ) r ON r.user_id = u.id
                    LEFT JOIN {coalition_src} cm ON cm.userid = u.id
                    LEFT JOIN coalitions c ON c.id = cm.colid
                    WHERE u.id > 0 {search_filter}
                )
                SELECT * FROM country_rows
            """

            range_filter = ""
            if province_range > 0:
                range_filter += " AND provinces_count <= %s"
                params.append(province_range)
            if upperinf is not None and lowerinf is not None and upperinf > 0 and lowerinf > 0:
                range_filter += " AND influence >= %s AND influence <= %s"
                params.extend([lowerinf, upperinf])

            count_query = f"SELECT COUNT(*) FROM ({filter_sql} {range_filter}) AS subquery"
            db.execute(count_query, params)
            total_count_row = db.fetchone()
            total_count = total_count_row[0] if total_count_row else 0
            
            total_pages = max(1, (total_count + per_page - 1) // per_page)
            if page < 1:
                page = 1
            elif page > total_pages:
                page = total_pages
            
            offset = (page - 1) * per_page
            
            final_query = f"""
                SELECT * FROM ({filter_sql} {range_filter}) AS subquery
                ORDER BY {sort_column} {sort_direction}, id {sort_direction}
                LIMIT %s OFFSET %s
            """
            final_params = list(params) + [per_page, offset]
            db.execute(final_query, final_params)
            
            raw_data = db.fetchall()
            
            return raw_data, total_count, total_pages, page
