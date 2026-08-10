from database import get_db_cursor, query_cache
from psycopg2.extras import RealDictCursor

class UserRepository:
    """All user-related database operations"""

    @staticmethod
    def get_full_user_data(user_id: int) -> dict:
        """Single query to get all user data needed for most pages"""
        cache_key = f"user_full_{user_id}"
        cached = query_cache.get(cache_key)
        if cached:
            return cached

        with get_db_cursor(cursor_factory=RealDictCursor) as db:
            db.execute("""
                SELECT
                    u.id, u.username, u.flag, u.date,
                    s.gold, s.location, s.governmentType,
                    m.soldiers, m.tanks, m.artillery, m.fighters, m.bombers,
                    m.apaches, m.destroyers, m.cruisers, m.submarines,
                    m.spies, m.ICBMs, m.nukes, m.manpower,
                    r.*
                FROM users u
                LEFT JOIN stats s ON u.id = s.id
                LEFT JOIN military m ON u.id = m.id
                LEFT JOIN resources r ON u.id = r.id
                WHERE u.id = %s
            """, (user_id,))
            result = dict(db.fetchone() or {})

        query_cache.set(cache_key, result)
        return result

    @staticmethod
    def get_provinces_summary(user_id: int) -> list:
        """Get all provinces for a user in one query"""
        cache_key = f"provinces_summary_{user_id}"
        cached = query_cache.get(cache_key)
        if cached:
            return cached

        with get_db_cursor(cursor_factory=RealDictCursor) as db:
            db.execute("""
                SELECT p.*, pi.*
                FROM provinces p
                LEFT JOIN proInfra pi ON p.id = pi.id
                WHERE p.userId = %s
                ORDER BY p.id
            """, (user_id,))
            result = [dict(row) for row in db.fetchall()]

        query_cache.set(cache_key, result)
        return result

    @staticmethod
    def invalidate_user_cache(user_id: int):
        """Clear all cached data for a user after mutations"""
        query_cache.invalidate(f"user_full_{user_id}")
        query_cache.invalidate(f"provinces_summary_{user_id}")
        query_cache.invalidate(f"influence_{user_id}")
        query_cache.invalidate(f"econ_stats_{user_id}")
        query_cache.invalidate(f"revenue_{user_id}")
