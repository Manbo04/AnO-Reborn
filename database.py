"""
Centralized Database Module for AnO
Provides connection pooling, query helpers, and unified database access patterns
"""

import psycopg2
from psycopg2.extras import RealDictCursor, execute_batch
import os
from contextlib import contextmanager
from typing import List, Dict, Any, Optional, Tuple
import logging
from functools import wraps
from time import time

# Load environment from .env (if present) before parsing DATABASE_URL
from dotenv import load_dotenv

# Ensure PG_* env vars are populated from DATABASE_URL (or DATABASE_PUBLIC_URL)
# for pool creation (force override)
from urllib.parse import urlparse, parse_qs

# Load environment from .env (if present) before parsing DATABASE_URL
load_dotenv()

db_url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
if db_url:
    parsed = urlparse(db_url)
    os.environ["PG_HOST"] = parsed.hostname or "localhost"
    os.environ["PG_PORT"] = str(parsed.port or "5432")
    os.environ["PG_USER"] = parsed.username or "postgres"
    os.environ["PG_PASSWORD"] = parsed.password or ""
    os.environ["PG_DATABASE"] = parsed.path[1:] if parsed.path else "postgres"
    # If the URL includes query parameters (e.g., sslmode=require), expose
    # the relevant option as PGSSLMODE so psycopg2 can use it.
    if parsed.query:
        q = parse_qs(parsed.query)
        sslmode = q.get("sslmode")
        if sslmode:
            os.environ["PGSSLMODE"] = sslmode[0]
else:
    # Lazy import here so load_dotenv() runs first and environment vars
    # from a .env file are available to config.parse_database_url().
    import config

    config.parse_database_url()  # fallback to original behavior

logger = logging.getLogger(__name__)
DEFAULT_CONNECT_TIMEOUT = int(os.getenv("PG_CONNECT_TIMEOUT", "10"))


# Simple query result cache for frequently accessed, slowly-changing data
class QueryCache:
    """Simple in-memory cache with TTL for database query results"""

    def __init__(self, ttl_seconds=300):  # 5 minute default TTL
        self.cache = {}
        self.ttl = ttl_seconds

    def get(self, key):
        """Get cached value if not expired"""
        if key in self.cache:
            value, timestamp = self.cache[key]
            if time() - timestamp < self.ttl:
                return value
            else:
                # expired: remove once and return None
                try:
                    del self.cache[key]
                except KeyError:
                    pass
        return None

    def set(self, key, value):
        """Cache a value with current timestamp"""
        self.cache[key] = (value, time())

    def invalidate(self, pattern=None):
        """Clear cache or clear entries matching pattern"""
        if pattern is None:
            self.cache.clear()
        else:
            # remove entries whose key contains the pattern
            keys_to_keep = {k: v for k, v in self.cache.items() if pattern not in k}
            self.cache = keys_to_keep


def cache_response(ttl_seconds=60):
    """
    Decorator to cache full page responses
    Useful for read-only pages that don't change frequently

    Usage:
        @cache_response(ttl_seconds=120)
        def my_page():
            # expensive DB queries
            return render_template(...)
    """

    def decorator(f):
        cache = {}

        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Create cache key from function name and user session
            from flask import session, request

            user_id = session.get("user_id", "anon")
            page_id = request.path if hasattr(request, "path") else ""
            cache_key = f"{f.__name__}_{user_id}_{page_id}"

            # Check if response is cached
            if cache_key in cache:
                response, timestamp = cache[cache_key]
                if time() - timestamp < ttl_seconds:
                    return response

            # Call actual function
            response = f(*args, **kwargs)

            # Cache the response
            cache[cache_key] = (response, time())
            return response

        return decorated_function

    return decorator


# Global query cache (5-minute TTL for slower-changing data)
query_cache = QueryCache(ttl_seconds=300)


class DatabasePool:
    """Singleton database connection pool"""

    _instance = None
    _pool = None
    _pid = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabasePool, cls).__new__(cls)
        return cls._instance

    def _initialize_pool(self):
        """Initialize the connection pool"""
        # If pool exists and is owned by this process pid, nothing to do
        current_pid = os.getpid()
        if self._pool is not None and self._pid == current_pid:
            return  # Already initialized in this process

        # If pool exists but belongs to a different (forked) process, close it
        if self._pool is not None and self._pid != current_pid:
            try:
                self._pool.closeall()
            except Exception:
                pass
            self._pool = None
        # Try to initialize the pool, with a small retry/backoff to avoid
        # hanging indefinitely if the DB is temporarily unavailable.
        retries = 3
        backoff = 1
        last_exc = None
        for attempt in range(1, retries + 1):
            try:
                try:
                    self._pool = psycopg2.pool.ThreadedConnectionPool(
                        minconn=1,
                        maxconn=50,
                        database=os.getenv("PG_DATABASE"),
                        user=os.getenv("PG_USER"),
                        password=os.getenv("PG_PASSWORD"),
                        host=os.getenv("PG_HOST"),
                        port=os.getenv("PG_PORT"),
                        sslmode=os.getenv("PGSSLMODE") or None,
                        connect_timeout=DEFAULT_CONNECT_TIMEOUT,
                    )
                except AttributeError:
                    # Some test environments provide a psycopg2 without the
                    # connection pool helper (e.g. minimal wheels). Fall back
                    # to a simple per-call connection helper to keep tests
                    # working without requiring the pool implementation.
                    class _SimplePool:
                        def getconn(self):
                            return psycopg2.connect(
                                database=os.getenv("PG_DATABASE"),
                                user=os.getenv("PG_USER"),
                                password=os.getenv("PG_PASSWORD"),
                                host=os.getenv("PG_HOST"),
                                port=os.getenv("PG_PORT"),
                                sslmode=os.getenv("PGSSLMODE") or None,
                                connect_timeout=DEFAULT_CONNECT_TIMEOUT,
                            )

                        def putconn(self, conn):
                            try:
                                conn.close()
                            except Exception:
                                pass

                        def closeall(self):
                            return

                    self._pool = _SimplePool()
                self._pid = os.getpid()
                logger.info(
                    "Database connection pool initialized (pid=%s) on attempt %s",
                    self._pid,
                    attempt,
                )
                last_exc = None
                break
            except Exception as e:
                last_exc = e
                logger.warning(
                    "Attempt %s/%s to initialize DB pool failed: %s",
                    attempt,
                    retries,
                    e,
                )
                # small backoff before retrying
                try:
                    import time as _time

                    _time.sleep(backoff)
                except Exception:
                    pass
                backoff *= 2

        if last_exc is not None:
            logger.error(
                "Failed to initialize database pool after retries: %s", last_exc
            )
            # Re-raise so calling code can decide how to proceed
            raise last_exc

    def get_connection(self):
        """Get a connection from the pool"""
        self._initialize_pool()  # Lazy init and fork-safe reinit
        return self._pool.getconn()

    def return_connection(self, conn):
        """Return a connection to the pool"""
        if self._pool is not None:
            try:
                self._pool.putconn(conn)
            except Exception as e:
                logger.error(f"Error returning connection to pool: {e}")
                # Try to close the connection if it can't be returned
                try:
                    conn.close()
                except Exception:
                    pass
        else:
            logger.warning("Attempted to return connection but pool is not initialized")
            # Close the connection to avoid leaks
            try:
                conn.close()
            except Exception:
                pass

    def close_all(self):
        """Close all connections in the pool"""
        if self._pool:
            self._pool.closeall()


# Global pool instance
db_pool = DatabasePool()


@contextmanager
def get_db_connection(cursor_factory=None):
    """
    Context manager for database connections

    Usage:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT ...")
    """
    conn = db_pool.get_connection()
    try:
        yield conn
        conn.commit()
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass  # Ignore rollback errors if connection is closed
        logger.error(f"Database error: {e}")
        raise
    finally:
        db_pool.return_connection(conn)


@contextmanager
def get_db_cursor(cursor_factory=None):
    """
    Context manager for database cursor

    Usage:
        with get_db_cursor() as cursor:
            cursor.execute("SELECT ...")
            results = cursor.fetchall()
    """
    # Try to use a pooled connection when possible, but fall back to
    # creating a dedicated connection if the pool isn't available or
    # if an error occurs. Using a dedicated connection for the cursor
    # prevents accidental reuse/closure races where a cursor from the
    # pool could be closed by another context.
    conn = None
    used_pool = False
    try:
        try:
            conn = db_pool.get_connection()
            used_pool = True
        except Exception:
            # Pool might not be initialized or available; create a fresh connection
            conn = psycopg2.connect(
                database=os.getenv("PG_DATABASE"),
                user=os.getenv("PG_USER"),
                password=os.getenv("PG_PASSWORD"),
                host=os.getenv("PG_HOST"),
                port=os.getenv("PG_PORT"),
                sslmode=os.getenv("PGSSLMODE") or None,
                connect_timeout=DEFAULT_CONNECT_TIMEOUT,
            )

        # If the connection appears closed for any reason, create a fresh one
        if getattr(conn, "closed", 0):
            try:
                conn.close()
            except Exception:
                pass
            conn = psycopg2.connect(
                database=os.getenv("PG_DATABASE"),
                user=os.getenv("PG_USER"),
                password=os.getenv("PG_PASSWORD"),
                host=os.getenv("PG_HOST"),
                port=os.getenv("PG_PORT"),
                sslmode=os.getenv("PGSSLMODE") or None,
                connect_timeout=DEFAULT_CONNECT_TIMEOUT,
            )

        cursor = conn.cursor(cursor_factory=cursor_factory)
        try:
            yield cursor
            conn.commit()
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            logger.error(f"Database error: {e}")
            raise
        finally:
            try:
                cursor.close()
            except Exception:
                pass
    finally:
        # Return or close the connection depending on how it was acquired
        try:
            if conn is not None:
                if used_pool:
                    try:
                        db_pool.return_connection(conn)
                    except Exception:
                        try:
                            conn.close()
                        except Exception:
                            pass
                else:
                    try:
                        conn.close()
                    except Exception:
                        pass
        except Exception:
            # Best-effort cleanup; don't let cleanup issues mask original errors
            pass


class QueryHelper:
    """Helper class for common database queries"""

    @staticmethod
    def fetch_one(
        query: str, params: tuple = None, dict_cursor: bool = False
    ) -> Optional[Any]:
        """Execute a query and fetch one result"""
        cursor_factory = RealDictCursor if dict_cursor else None
        with get_db_cursor(cursor_factory=cursor_factory) as cursor:
            cursor.execute(query, params)
            return cursor.fetchone()

    @staticmethod
    def fetch_all(
        query: str, params: tuple = None, dict_cursor: bool = False
    ) -> List[Any]:
        """Execute a query and fetch all results"""
        cursor_factory = RealDictCursor if dict_cursor else None
        with get_db_cursor(cursor_factory=cursor_factory) as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()

    @staticmethod
    def execute(query: str, params: tuple = None) -> None:
        """Execute a query without fetching results"""
        with get_db_cursor() as cursor:
            cursor.execute(query, params)

    @staticmethod
    def execute_many(query: str, params_list: List[tuple]) -> None:
        """Execute a query with multiple parameter sets
        using execute_batch for efficiency
        """
        with get_db_cursor() as cursor:
            execute_batch(cursor, query, params_list)

    @staticmethod
    def execute_returning(query: str, params: tuple = None) -> Any:
        """Execute a query and return the result (useful for INSERT ... RETURNING)"""
        with get_db_cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchone()


class UserQueries:
    """Optimized queries for user-related operations"""

    @staticmethod
    def get_user_resources(user_id: int) -> Dict[str, int]:
        """Get all resources for a user in a single query"""
        query = """
            SELECT rations, oil, coal, uranium, bauxite, iron, lead, copper,
                   lumber, components, steel, consumer_goods,
                   aluminium, gasoline, ammunition
            FROM resources WHERE id = %s
        """
        result = QueryHelper.fetch_one(query, (user_id,), dict_cursor=True)
        return dict(result) if result else {}

    @staticmethod
    def get_user_military(user_id: int) -> Dict[str, int]:
        """Get all military units for a user in a single query"""
        query = """
            SELECT soldiers, artillery, tanks, bombers, fighters, apaches,
                   spies, ICBMs, nukes, destroyers, cruisers, submarines,
                   manpower, army_tradition, defcon, default_defense
            FROM military WHERE id = %s
        """
        result = QueryHelper.fetch_one(query, (user_id,), dict_cursor=True)
        return dict(result) if result else {}

    @staticmethod
    def get_user_stats(user_id: int) -> Dict[str, Any]:
        """Get user stats in a single query"""
        query = "SELECT gold FROM stats WHERE id = %s"
        result = QueryHelper.fetch_one(query, (user_id,))
        return {"gold": result[0]} if result else {"gold": 0}

    @staticmethod
    def get_all_user_ids() -> List[int]:
        """Get all user IDs efficiently"""
        query = "SELECT id FROM users"
        results = QueryHelper.fetch_all(query)
        return [row[0] for row in results]


class ProvinceQueries:
    """Optimized queries for province-related operations"""

    @staticmethod
    def get_user_provinces_summary(user_id: int) -> Dict[str, Any]:
        """Get aggregated province data for a user in a single query"""
        query = """
            SELECT
                COUNT(id) as province_count,
                COALESCE(SUM(population), 0) as total_population,
                COALESCE(SUM(land), 0) as total_land,
                COALESCE(SUM(cityCount), 0) as total_cities,
                COALESCE(AVG(happiness), 0) as avg_happiness,
                COALESCE(AVG(productivity), 0) as avg_productivity
            FROM provinces
            WHERE userId = %s
        """
        result = QueryHelper.fetch_one(query, (user_id,), dict_cursor=True)
        return dict(result) if result else {}

    @staticmethod
    def get_user_provinces_with_infrastructure(user_id: int) -> List[Dict[str, Any]]:
        """Get all provinces with their infrastructure in a single JOIN query"""
        query = """
            SELECT
                p.id, p.provinceName, p.population, p.land, p.cityCount,
                p.energy, p.happiness, p.pollution, p.productivity, p.consumer_spending,
                pi.*
            FROM provinces p
            LEFT JOIN proInfra pi ON p.id = pi.id
            WHERE p.userId = %s
            ORDER BY p.id
        """
        results = QueryHelper.fetch_all(query, (user_id,), dict_cursor=True)
        return [dict(row) for row in results]

    @staticmethod
    def get_province_ids_by_user(user_id: int) -> List[int]:
        """Get all province IDs for a user efficiently"""
        query = "SELECT id FROM provinces WHERE userId = %s ORDER BY id"
        results = QueryHelper.fetch_all(query, (user_id,))
        return [row[0] for row in results]

    @staticmethod
    def get_total_infrastructure_by_user(user_id: int) -> Dict[str, int]:
        """Get total infrastructure counts for a user in a single aggregated query"""
        query = """
            SELECT
                SUM(pi.coal_burners) AS coal_burners,
                SUM(pi.oil_burners) AS oil_burners,
                SUM(pi.hydro_dams) AS hydro_dams,
                SUM(pi.nuclear_reactors) AS nuclear_reactors,
                SUM(pi.solar_fields) AS solar_fields,
                SUM(pi.gas_stations) AS gas_stations,
                SUM(pi.general_stores) AS general_stores,
                SUM(pi.farmers_markets) AS farmers_markets,
                SUM(pi.malls) AS malls,
                SUM(pi.banks) AS banks,
                SUM(pi.city_parks) AS city_parks,
                SUM(pi.hospitals) AS hospitals,
                SUM(pi.libraries) AS libraries,
                SUM(pi.universities) AS universities,
                SUM(pi.monorails) AS monorails,
                SUM(pi.army_bases) AS army_bases,
                SUM(pi.harbours) AS harbours,
                SUM(pi.aerodomes) AS aerodomes,
                SUM(pi.admin_buildings) AS admin_buildings,
                SUM(pi.silos) AS silos,
                SUM(pi.farms) AS farms,
                SUM(pi.pumpjacks) AS pumpjacks,
                SUM(pi.coal_mines) AS coal_mines,
                SUM(pi.bauxite_mines) AS bauxite_mines,
                SUM(pi.copper_mines) AS copper_mines,
                SUM(pi.uranium_mines) AS uranium_mines,
                SUM(pi.lead_mines) AS lead_mines,
                SUM(pi.iron_mines) AS iron_mines,
                SUM(pi.lumber_mills) AS lumber_mills,
                SUM(pi.component_factories) AS component_factories,
                SUM(pi.steel_mills) AS steel_mills,
                SUM(pi.ammunition_factories) AS ammunition_factories,
                SUM(pi.aluminium_refineries) AS aluminium_refineries,
                SUM(pi.oil_refineries) AS oil_refineries
            FROM proInfra pi
            LEFT JOIN provinces p ON pi.id = p.id
            WHERE p.userId = %s
        """
        result = QueryHelper.fetch_one(query, (user_id,), dict_cursor=True)
        return dict(result) if result else {}


class CoalitionQueries:
    """Optimized queries for coalition-related operations"""

    @staticmethod
    def get_coalition_members(coalition_id: int) -> List[Dict[str, Any]]:
        """Get all coalition members with their roles in a single query"""
        query = """
            SELECT c.userId, c.role, u.username
            FROM coalitions c
            JOIN users u ON c.userId = u.id
            WHERE c.colId = %s
            ORDER BY
                CASE c.role
                    WHEN 'leader' THEN 1
                    WHEN 'deputy_leader' THEN 2
                    WHEN 'domestic_minister' THEN 3
                    WHEN 'banker' THEN 4
                    WHEN 'tax_collector' THEN 5
                    WHEN 'foreign_ambassador' THEN 6
                    WHEN 'general' THEN 7
                    ELSE 8
                END
        """
        results = QueryHelper.fetch_all(query, (coalition_id,), dict_cursor=True)
        return [dict(row) for row in results]

    @staticmethod
    def get_coalition_influence(coalition_id: int) -> int:
        """Calculate total coalition influence efficiently"""
        # This would need the influence calculation logic, but we can
        # pre-aggregate much of it
        query = """
            SELECT
                c.userId,
                COALESCE(SUM(p.cityCount), 0) * 10 as cities_score,
                COALESCE(SUM(p.land), 0) * 10 as land_score,
                COUNT(p.id) * 300 as provinces_score
            FROM coalitions c
            LEFT JOIN provinces p ON c.userId = p.id
            WHERE c.colId = %s
            GROUP BY c.userId
        """
        results = QueryHelper.fetch_all(query, (coalition_id,), dict_cursor=True)
        # Would need to add military and resource scores
        return results

    @staticmethod
    def get_coalition_bank_resources(coalition_id: int) -> Dict[str, int]:
        """Get all coalition bank resources in a single query"""
        query = """
            SELECT rations, oil, coal, uranium, bauxite, iron, lead, copper,
                   lumber, components, steel, consumer_goods, aluminium, gasoline,
                   ammunition, money
            FROM colBanks WHERE colId = %s
        """
        result = QueryHelper.fetch_one(query, (coalition_id,), dict_cursor=True)
        return dict(result) if result else {}


class BatchOperations:
    """Helper class for batch database operations"""

    @staticmethod
    def batch_update_resources(user_resources: List[Tuple[int, str, int]]) -> None:
        """
        Batch update resources for multiple users

        Args:
            user_resources: List of tuples (user_id, resource_name, amount)
        """
        # Group updates by resource type for efficiency
        from collections import defaultdict

        grouped = defaultdict(list)

        for user_id, resource, amount in user_resources:
            grouped[resource].append((amount, user_id))

        for resource, updates in grouped.items():
            query = f"UPDATE resources SET {resource} = {resource} + %s WHERE id = %s"
            QueryHelper.execute_many(query, updates)

    @staticmethod
    def batch_update_military(user_units: List[Tuple[int, str, int]]) -> None:
        """
        Batch update military units for multiple users

        Args:
            user_units: List of tuples (user_id, unit_type, amount)
        """
        from collections import defaultdict

        grouped = defaultdict(list)

        for user_id, unit_type, amount in user_units:
            grouped[unit_type].append((amount, user_id))

        for unit_type, updates in grouped.items():
            query = f"UPDATE military SET {unit_type} = {unit_type} + %s WHERE id = %s"
            QueryHelper.execute_many(query, updates)


# Utility functions for common operations
def get_user_full_data(user_id: int) -> Dict[str, Any]:
    """Get all user data in optimized queries"""
    return {
        "resources": UserQueries.get_user_resources(user_id),
        "military": UserQueries.get_user_military(user_id),
        "stats": UserQueries.get_user_stats(user_id),
        "provinces": ProvinceQueries.get_user_provinces_summary(user_id),
    }


# Convenience helper used by tasks to safely read the first column of a
# previously-executed cursor. Many code paths expect a simple value and
# historically did `row = cursor.fetchone()[0]` which raises when no row is
# returned. This helper centralizes the safe pattern.
def fetchone_first(cursor, default=None):
    """Return the first column of the fetched row or `default` if no row.

    Args:
        cursor: DB cursor that has just executed a query.
        default: Value to return when no row is present.

    Returns:
        The first column of the row or `default`.
    """
    row = cursor.fetchone()
    if not row:
        return default
    try:
        return row[0]
    except Exception:
        # Defensive fallback in case row is e.g. a mapping
        # Try to get a value if possible, else return default
        try:
            return next(iter(row.values()))
        except Exception:
            return default


def close_database_pool():
    """Close all database connections (call on application shutdown)"""
    db_pool.close_all()
