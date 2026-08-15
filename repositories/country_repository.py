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
                WITH user_ids AS (
                    SELECT id FROM users u WHERE u.id > 0 {search_filter}
                ),
                country_rows AS (
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
                    JOIN user_ids ui ON u.id = ui.id
                    LEFT JOIN stats s ON s.id = u.id
                    LEFT JOIN LATERAL (
                        SELECT
                            COUNT(id) AS provinces_count,
                            COALESCE(SUM(population), 0) AS province_population,
                            COALESCE(SUM(citycount), 0) AS city_count,
                            COALESCE(SUM(land), 0) AS total_land
                        FROM provinces
                        WHERE userid = u.id
                    ) p ON true
                    LEFT JOIN LATERAL (
                        SELECT
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
                        FROM user_military um
                        JOIN unit_dictionary ud ON um.unit_id = ud.unit_id
                        WHERE um.user_id = u.id
                    ) m ON true
                    LEFT JOIN LATERAL (
                        SELECT COALESCE(SUM(quantity), 0) AS total_resources
                        FROM user_economy
                        WHERE user_id = u.id
                    ) r ON true
                    LEFT JOIN {coalition_src} cm ON cm.userid = u.id
                    LEFT JOIN coalitions c ON c.coalition_id = cm.colid
                )
                SELECT * FROM country_rows WHERE 1=1
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

    @staticmethod
    def delete_news(news_id: int, user_id: int):
        with get_request_cursor() as db:
            db.execute(
                "DELETE FROM news WHERE id=%s AND destination_id=%s",
                (news_id, user_id)
            )

    @staticmethod
    def delete_own_account(cId: int):
        with get_request_cursor() as db:
            # Track how many rows we delete from key tables for observability
            deleted_counts = {}

            db.execute("DELETE FROM referral_active_days WHERE referred_user_id=%s", (cId,))
            deleted_counts["referral_active_days"] = db.rowcount
            db.execute(
                "DELETE FROM referral_milestone_payouts "
                "WHERE referrer_user_id=%s OR referred_user_id=%s",
                (cId, cId),
            )
            deleted_counts["referral_milestone_payouts"] = db.rowcount
            db.execute(
                "UPDATE users SET referred_by_user_id=NULL WHERE referred_by_user_id=%s",
                (cId,),
            )
            deleted_counts["referred_by_user_id_cleared"] = db.rowcount

            db.execute("DELETE FROM users WHERE id=(%s)", (cId,))
            deleted_counts["users"] = db.rowcount
            db.execute("DELETE FROM stats WHERE id=(%s)", (cId,))
            deleted_counts["stats"] = db.rowcount
            db.execute("DELETE FROM user_military WHERE user_id=(%s)", (cId,))
            deleted_counts["user_military"] = db.rowcount
            db.execute("DELETE FROM user_economy WHERE user_id=(%s)", (cId,))
            deleted_counts["user_economy"] = db.rowcount

            db.execute("DELETE FROM offers WHERE user_id=(%s)", (cId,))
            deleted_counts["offers"] = db.rowcount
            db.execute(
                "DELETE FROM wars WHERE defender=%s OR attacker=%s", (cId, cId)
            )
            deleted_counts["wars"] = db.rowcount

            db.execute("SELECT id FROM provinces WHERE userid=%s", (cId,))
            province_ids = db.fetchall()
            if province_ids:
                ids = [p[0] for p in province_ids]
                placeholders = ",".join(["%s"] * len(ids))
                db.execute(
                    f"DELETE FROM provinces WHERE id IN ({placeholders})", tuple(ids)
                )
                deleted_counts["provinces"] = db.rowcount

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
                from app_core.coalitions.repositories import get_user_role
                coalition_role = get_user_role(cId)
            except Exception:
                coalition_role = None
                
            from database import get_coalition_members_table
            members_tbl = get_coalition_members_table()
            
            if coalition_role == "leader" and members_tbl:
                col_colid = "coalition_id" if members_tbl == "coalition_members" else "colid"
                col_userid = "user_id" if members_tbl == "coalition_members" else "userid"
                
                db.execute(
                    f"SELECT {col_colid} FROM {members_tbl} WHERE {col_userid}=%s", (cId,)
                )
                coalition_row = db.fetchone()
                if coalition_row:
                    user_coalition = coalition_row[0]
                    db.execute(
                        f"SELECT COUNT({col_userid}) FROM {members_tbl} "
                        f"WHERE role='leader' AND {col_colid}=%s",
                        (user_coalition,),
                    )
                    leader_row = db.fetchone()
                    leader_count = leader_row[0] if leader_row else 0
                    if leader_count == 1:
                        db.execute(
                            f"DELETE FROM {members_tbl} WHERE {col_colid}=%s",
                            (user_coalition,),
                        )
                        db.execute("DELETE FROM colNames WHERE id=%s", (user_coalition,))
                        db.execute("DELETE FROM colBanks WHERE colId=%s", (user_coalition,))
                        db.execute("DELETE FROM requests WHERE colId=%s", (user_coalition,))

            if members_tbl:
                col_userid = "user_id" if members_tbl == "coalition_members" else "userid"
                db.execute(f"DELETE FROM {members_tbl} WHERE {col_userid}=%s", (cId,))
            db.execute("DELETE FROM colBanksRequests WHERE reqId=%s", (cId,))

            db.execute("DELETE FROM user_tech WHERE user_id=%s", (cId,))
            deleted_counts["user_tech"] = db.rowcount
            db.execute("DELETE FROM policies WHERE user_id=%s", (cId,))
            deleted_counts["policies"] = db.rowcount
            db.execute("DELETE FROM news WHERE destination_id=%s", (cId,))
            deleted_counts["news"] = db.rowcount

            return True, deleted_counts
