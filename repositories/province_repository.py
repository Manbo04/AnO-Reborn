from database import get_request_cursor, query_cache
from psycopg2.extras import RealDictCursor

class ProvinceRepository:
    """Province-related database operations"""

    @staticmethod
    def get_provinces_paginated(user_id: int, page: int, per_page: int, has_image_col: str) -> tuple:
        with get_request_cursor(read_only=True) as db:
            db.execute("SELECT COUNT(*) FROM provinces WHERE userId=(%s)", (user_id,))
            total_count = db.fetchone()
            total_count = total_count[0] if total_count else 0
            
            total_pages = max(1, (total_count + per_page - 1) // per_page)
            if page < 1:
                page = 1
            elif page > total_pages:
                page = total_pages
                
            offset = (page - 1) * per_page
            
            db.execute(
                (
                    f"SELECT CAST(citycount AS INTEGER) AS citycount, population, "
                    f"provinceName, id, land, happiness, "
                    f"productivity, energy{has_image_col} "
                    f"FROM provinces WHERE userId=(%s) ORDER BY id ASC LIMIT %s OFFSET %s"
                ),
                (user_id, per_page, offset),
            )
            provinces_raw = db.fetchall()
            
            return provinces_raw, total_count, total_pages, page
