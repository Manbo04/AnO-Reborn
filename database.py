"""
Centralized Database Module for AnO
Provides connection pooling, query helpers, and unified database access patterns
"""

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor, execute_batch
import os
from contextlib import contextmanager
from dotenv import load_dotenv
from typing import List, Dict, Any, Optional, Tuple
import logging
from functools import lru_cache, wraps
from time import time
import threading
import queue

load_dotenv()
import config  # Parse Railway DATABASE_URL

# Ensure PG_* env vars are populated from DATABASE_URL (or DATABASE_PUBLIC_URL) for pool creation (force override)
from urllib.parse import urlparse

db_url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
if db_url:
    parsed = urlparse(db_url)
    os.environ["PG_HOST"] = parsed.hostname or "localhost"
    os.environ["PG_PORT"] = str(parsed.port or "5432")
    os.environ["PG_USER"] = parsed.username or "postgres"
    os.environ["PG_PASSWORD"] = parsed.password or ""
    os.environ["PG_DATABASE"] = parsed.path[1:] if parsed.path else "postgres"
else:
    config.parse_database_url()  # fallback to original behavior

logger = logging.getLogger(__name__)


# Simple query result cache for frequently accessed, slowly-changing data
class QueryCache:
    """Simple in-memory cache with TTL for database query results"""

    MAX_CACHE_SIZE = 10000  # Prevent unbounded memory growth

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
        # Evict expired entries periodically to prevent unbounded growth
        if len(self.cache) > self.MAX_CACHE_SIZE:
            self._evict_expired()
        # If still over limit, clear oldest half
        if len(self.cache) > self.MAX_CACHE_SIZE:
            self._evict_oldest(len(self.cache) // 2)
        self.cache[key] = (value, time())

    def _evict_expired(self):
        """Remove all expired entries"""
        current_time = time()
        self.cache = {
            k: v for k, v in self.cache.items() if current_time - v[1] < self.ttl
        }

    def _evict_oldest(self, count):
        """Remove the oldest n entries"""
        if count <= 0 or not self.cache:
            return
        sorted_keys = sorted(self.cache.keys(), key=lambda k: self.cache[k][1])
        for key in sorted_keys[:count]:
            try:
                del self.cache[key]
            except KeyError:
                pass

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


def fetchone_first(db, default=None):
    """Fetch a single row and return its first column/value or a default.

    Compatibility helper: works with simple tuple rows or dict-like rows
    (e.g., psycopg2.extras.RealDictCursor). Returns `default` if no row
    is returned.
    """
    row = db.fetchone()
    if not row:
        return default
    # tuple/list-like row
    if isinstance(row, (list, tuple)):
        return row[0]
    # dict-like row: return the first value encountered
    if isinstance(row, dict):
        return next(iter(row.values()))
    # Fallback: return the row itself
    return row


# Global query cache (5-minute TTL for slower-changing data)
query_cache = QueryCache(ttl_seconds=300)


class DatabasePool:
    """Singleton database connection pool with timeout support"""

    _instance = None
    _pool = None
    _pid = None
    _lock = None
    _available = None  # Semaphore-like queue for timeout support
    CONNECTION_TIMEOUT = 10  # seconds to wait for connection before giving up

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabasePool, cls).__new__(cls)
            cls._instance._lock = threading.Lock()
        return cls._instance

    def _initialize_pool(self):
        """Initialize the connection pool"""
        # If pool exists and is owned by this process pid, nothing to do
        current_pid = os.getpid()
        if self._pool is not None and self._pid == current_pid:
            return  # Already initialized in this process

        with self._lock:
            # Double-check inside lock
            if self._pool is not None and self._pid == current_pid:
                return

            # If pool exists but belongs to a different (forked) process, close it
            if self._pool is not None and self._pid != current_pid:
                try:
                    self._pool.closeall()
                except Exception:
                    pass
                self._pool = None
                self._available = None

            try:
                # With multiple instances (EU, Singapore, etc.), use fewer connections per instance
                maxconn = int(os.getenv("DB_MAX_CONNECTIONS", "20"))
                self._pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn=1,
                    maxconn=maxconn,
                    database=os.getenv("PG_DATABASE"),
                    user=os.getenv("PG_USER"),
                    password=os.getenv("PG_PASSWORD"),
                    host=os.getenv("PG_HOST"),
                    port=os.getenv("PG_PORT"),
                    # Connection timeout settings to prevent hanging
                    connect_timeout=10,  # 10 seconds to establish connection
                    options="-c statement_timeout=30000",  # 30 second query timeout
                    # TCP keepalive settings to detect dead connections
                    keepalives=1,  # Enable TCP keepalives
                    keepalives_idle=30,  # Send keepalive after 30 seconds idle
                    keepalives_interval=10,  # Retry every 10 seconds
                    keepalives_count=3,  # Give up after 3 failed keepalives
                )
                # Create a queue to track available slots with timeout support
                self._available = queue.Queue(maxsize=maxconn)
                for _ in range(maxconn):
                    self._available.put(True)

                self._pid = os.getpid()
                logger.info(
                    "Database connection pool initialized (pid=%s, max=%d)",
                    self._pid,
                    maxconn,
                )
            except Exception as e:
                logger.error(f"Failed to initialize database pool: {e}")
                raise

    def get_connection(self, timeout=None):
        """Get a connection from the pool with timeout support

        Args:
            timeout: Maximum seconds to wait for a connection.
                     Defaults to CONNECTION_TIMEOUT (10s).

        Raises:
            TimeoutError: If no connection available within timeout
            Exception: If pool cannot be initialized
        """
        if timeout is None:
            timeout = self.CONNECTION_TIMEOUT

        self._initialize_pool()  # Lazy init and fork-safe reinit

        # Wait for an available slot with timeout
        try:
            self._available.get(timeout=timeout)
        except queue.Empty:
            logger.error(
                f"Database connection pool exhausted, timed out after {timeout}s"
            )
            raise TimeoutError(f"Database connection pool exhausted, waited {timeout}s")

        try:
            conn = self._pool.getconn()
            # Validate connection is still alive
            if conn.closed or not self._is_connection_healthy(conn):
                logger.warning(
                    "Retrieved stale connection from pool, getting fresh one"
                )
                try:
                    conn.close()
                except Exception:
                    pass
                # Try to get a new connection by putting one back and re-getting
                self._pool.putconn(conn, close=True)
                conn = self._pool.getconn()
            return conn
        except Exception as e:
            # Put the slot back if we failed to get connection
            try:
                self._available.put(True, block=False)
            except queue.Full:
                pass
            raise

    def _is_connection_healthy(self, conn):
        """Check if a connection is still usable"""
        try:
            # Quick health check - execute a simple query
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
            cur.close()
            return True
        except Exception:
            return False

    def return_connection(self, conn, close=False):
        """Return a connection to the pool

        Args:
            conn: The connection to return
            close: If True, close the connection instead of returning to pool
        """
        if self._pool is not None:
            try:
                # Check if connection is broken/closed
                if conn.closed or close:
                    # Close and remove from pool instead of returning bad connection
                    self._pool.putconn(conn, close=True)
                else:
                    self._pool.putconn(conn)
            except Exception as e:
                logger.error(f"Error returning connection to pool: {e}")
                # Try to close the connection if it can't be returned
                try:
                    conn.close()
                except Exception:
                    pass
            finally:
                # Mark slot as available
                if self._available is not None:
                    try:
                        self._available.put(True, block=False)
                    except queue.Full:
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
    close_on_return = False
    try:
        yield conn
        conn.commit()
    except (psycopg2.InterfaceError, psycopg2.OperationalError) as e:
        # Connection-level error - mark for closure
        close_on_return = True
        logger.error(f"Database connection error: {e}")
        raise
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            close_on_return = True  # Connection may be broken
        logger.error(f"Database error: {e}")
        raise
    finally:
        db_pool.return_connection(conn, close=close_on_return)


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
    close_on_return = False
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
                connect_timeout=10,
                keepalives=1,
                keepalives_idle=30,
                keepalives_interval=10,
                keepalives_count=3,
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
                connect_timeout=10,
                keepalives=1,
                keepalives_idle=30,
                keepalives_interval=10,
                keepalives_count=3,
            )
            used_pool = False

        cursor = conn.cursor(cursor_factory=cursor_factory)
        try:
            yield cursor
            conn.commit()
        except (psycopg2.InterfaceError, psycopg2.OperationalError) as e:
            # Connection-level error - mark for closure
            close_on_return = True
            logger.error(f"Database connection error in cursor: {e}")
            raise
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                close_on_return = True
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
                        db_pool.return_connection(conn, close=close_on_return)
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
        """Execute a query with multiple parameter sets using execute_batch for efficiency"""
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
                   lumber, components, steel, consumer_goods, aluminium, gasoline, ammunition
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
        # This would need the influence calculation logic, but we can pre-aggregate much of it
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


def close_database_pool():
    """Close all database connections (call on application shutdown)"""
    db_pool.close_all()
