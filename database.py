"""
Centralized Database Module for AnO
Provides connection pooling, query helpers, and unified database access patterns
"""

import psycopg2
from psycopg2.extras import RealDictCursor, execute_batch
import os
from contextlib import contextmanager
from dotenv import load_dotenv
from typing import List, Dict, Any, Optional, Tuple
import logging
from functools import wraps
from time import time
import threading
import queue
from urllib.parse import urlparse
from collections import OrderedDict

load_dotenv()
import config  # Parse Railway DATABASE_URL  # noqa: E402

# Ensure PG_* env vars are populated from DATABASE_URL (or DATABASE_PUBLIC_URL).
# Parse and set PG_* environment variables used by the connection pool below.

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
    """Simple in-memory cache with optional per-key TTL support.

    Each cache entry is stored as (value, expiry_timestamp). Per-key TTLs may
    override the instance default for specific items.
    Thread-safe: uses a lock for all mutations.
    """

    MAX_CACHE_SIZE = 10000  # Prevent unbounded memory growth

    def __init__(self, ttl_seconds=300):  # default TTL (seconds)
        self.cache = {}  # key -> (value, expiry_timestamp)
        self.ttl = ttl_seconds
        self._lock = threading.Lock()

    def get(self, key):
        """Get cached value if not expired. Returns None if missing/expired."""
        entry = self.cache.get(key)
        if not entry:
            return None
        value, expiry = entry
        # expiry == 0 means 'never expire'
        if expiry == 0 or time() < expiry:
            return value
        # expired - remove and return None
        with self._lock:
            try:
                del self.cache[key]
            except KeyError:
                pass
        return None

    def set(self, key, value, ttl_seconds: Optional[int] = None):
        """Cache a value with an optional per-key TTL in seconds.

        If ttl_seconds is None, the instance default TTL is used. If ttl_seconds
        is 0, the value will not expire (use with caution).
        """
        with self._lock:
            # Evict expired entries periodically to prevent unbounded growth
            if len(self.cache) > self.MAX_CACHE_SIZE:
                self._evict_expired()
            # If still over limit, clear oldest half
            if len(self.cache) > self.MAX_CACHE_SIZE:
                self._evict_oldest(len(self.cache) // 2)

            if ttl_seconds is None:
                ttl_seconds = self.ttl
            expiry = 0 if ttl_seconds == 0 else (time() + ttl_seconds)
            self.cache[key] = (value, expiry)

    def _evict_expired(self):
        """Remove all expired entries (caller must hold _lock)"""
        current_time = time()
        self.cache = {
            k: v for k, v in self.cache.items() if v[1] == 0 or current_time < v[1]
        }

    def _evict_oldest(self, count):
        """Remove the oldest n entries (caller must hold _lock)"""
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
        with self._lock:
            if pattern is None:
                self.cache.clear()
            else:
                # remove entries whose key contains the pattern
                self.cache = {k: v for k, v in self.cache.items() if pattern not in k}


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
        cache = OrderedDict()
        max_entries = int(os.getenv("RESPONSE_CACHE_MAX_ENTRIES", "500"))

        def _evict_expired_entries(now_ts):
            expired = [k for k, (_, ts) in cache.items() if now_ts - ts >= ttl_seconds]
            for k in expired:
                try:
                    del cache[k]
                except KeyError:
                    pass

        def _enforce_size_limit():
            while len(cache) > max_entries:
                try:
                    cache.popitem(last=False)
                except Exception:
                    break

        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Create cache key from function name and user session
            from flask import session, request

            user_id = session.get("user_id", "anon")
            # Include full URL with query string so different
            # pages/filters get cached separately
            page_id = request.full_path if hasattr(request, "full_path") else ""
            cache_key = f"{f.__name__}_{user_id}_{page_id}"

            # Check if response is cached
            if cache_key in cache:
                response, timestamp = cache[cache_key]
                if time() - timestamp < ttl_seconds:
                    cache.move_to_end(cache_key)
                    return response
                try:
                    del cache[cache_key]
                except KeyError:
                    pass

            # Call actual function
            response = f(*args, **kwargs)

            # Cache the response
            cache[cache_key] = (response, time())
            cache.move_to_end(cache_key)
            # Best-effort cleanup to keep memory bounded.
            now_ts = time()
            if len(cache) > max_entries:
                _evict_expired_entries(now_ts)
            _enforce_size_limit()
            return response

        # Expose the internal cache and invalidation helpers on the decorated
        # function so callers (routes/handlers) can invalidate cached pages
        # when underlying data changes (e.g. role changes, join requests).
        decorated_function._response_cache = cache
        # Register the cache so other modules can invalidate it even if they
        # don't have a direct reference to the decorated function object.
        response_cache_registry[f.__name__] = cache

        def invalidate(
            pattern: str | None = None,
            user_id: int | None = None,
            page: str | None = None,
        ):
            """Invalidate cached responses for this decorated view.

            - pattern: substring to match against cache keys
            - user_id: remove keys for a specific user id
            - page: remove keys which include the page path (e.g. '/coalition/2')

            If multiple arguments are provided they are OR'ed (any match will
            cause removal). If all are None the entire cache for this view is
            cleared.
            """

            keys = list(cache.keys())
            for k in keys:
                remove = False
                if pattern and pattern in k:
                    remove = True
                if user_id is not None and f"_{user_id}_" in k:
                    remove = True
                if page and page in k:
                    remove = True
                if pattern is None and user_id is None and page is None:
                    remove = True

                if remove:
                    try:
                        del cache[k]
                    except KeyError:
                        pass

        def clear_cache():
            """Clear the full cache for this decorated view."""

            cache.clear()

        decorated_function.invalidate = invalidate
        decorated_function.clear_cache = clear_cache

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

# Registry for per-view response caches created by `cache_response`.
# Maps view function name -> the internal `cache` dict used by the decorator.
response_cache_registry: Dict[str, dict] = {}


def invalidate_view_cache(
    view_name: str,
    user_id: int | None = None,
    page: str | None = None,
    pattern: str | None = None,
) -> None:
    """Invalidate entries from a cached view response registry.

    This is a helper so route handlers can clear cached HTML responses when
    related data changes (e.g. role changes, join requests). It is resilient
    if a view has no registered cache.
    """
    cache = response_cache_registry.get(view_name)
    if not cache:
        return
    keys = list(cache.keys())
    for k in keys:
        remove = False
        if pattern and pattern in k:
            remove = True
        if user_id is not None and f"_{user_id}_" in k:
            remove = True
        if page and page in k:
            remove = True
        if pattern is None and user_id is None and page is None:
            remove = True
        if remove:
            try:
                del cache[k]
            except KeyError:
                pass


def invalidate_user_cache(user_id: int) -> None:
    """Invalidate common caches related to a specific user.

    This removes cached resources and influence entries for the given user id.
    Use when user resources, provinces, or stats are updated to ensure
    subsequent reads return fresh data.

    This function is defensive: it tries a direct key delete first and falls
    back to pattern-based invalidation to tolerate tests and edge cases.
    """
    key_res = f"resources_{user_id}"
    key_inf = f"influence_{user_id}"
    try:
        # Directly remove exact keys when present
        if key_res in query_cache.cache:
            del query_cache.cache[key_res]
        else:
            query_cache.invalidate(pattern=key_res)
    except Exception as e:
        logger.exception("Failed to invalidate resources cache for %s: %s", user_id, e)

    try:
        if key_inf in query_cache.cache:
            del query_cache.cache[key_inf]
        else:
            query_cache.invalidate(pattern=key_inf)
    except Exception as e:
        logger.exception("Failed to invalidate influence cache for %s: %s", user_id, e)


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
                # In multi-region deployments (EU, Singapore, ...),
                # use fewer connections per instance
                maxconn = int(os.getenv("DB_MAX_CONNECTIONS", "20"))
                # Use psycopg2's ThreadedConnectionPool if available; otherwise
                # fall back to a lightweight compatibility pool (useful in some
                # CI environments where a minimal psycopg2 shim may be present).
                try:
                    pool_cls = psycopg2.pool.ThreadedConnectionPool
                except Exception:
                    # Minimal compatibility pool: creates connections on demand
                    class _CompatPool:
                        def __init__(self, minconn, maxconn, **kwargs):
                            self.minconn = minconn
                            self.maxconn = maxconn
                            self._kwargs = kwargs

                        def getconn(self):
                            return psycopg2.connect(**self._kwargs)

                        def putconn(self, conn, close=False):
                            try:
                                if close or getattr(conn, "closed", False):
                                    conn.close()
                            except Exception:
                                pass

                        def closeall(self):
                            return

                    pool_cls = _CompatPool

                self._pool = pool_cls(
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
                    keepalives_idle=30,  # Sendkeepalive after 30 seconds idle
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
        except Exception:
            # Put the slot back if we failed to get connection
            try:
                self._available.put(True, block=False)
            except queue.Full:
                pass
            raise

    def _is_connection_healthy(self, conn):
        """Check if a connection is still usable.

        Uses the libpq connection status check first (no round-trip),
        only falling back to SELECT 1 if the status is ambiguous.
        """
        try:
            # Fast check: use libpq status (no network round-trip)
            if conn.closed:
                return False
            # Check transaction status — if connection is in a bad state
            # (e.g. InFailedTransaction), it's not healthy
            status = conn.info.transaction_status
            if status == psycopg2.extensions.TRANSACTION_STATUS_INERROR:
                return False
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
    import logging

    logging.getLogger(__name__).debug(
        "get_db_connection: got conn type=%s closed=%s",
        type(conn),
        getattr(conn, "closed", None),
    )
    close_on_return = False
    try:
        yield conn
        conn.commit()
    except (psycopg2.InterfaceError, psycopg2.OperationalError) as e:
        # Connection-level error - mark for closure
        close_on_return = True
        logger.error(f"Database connection error: {e}")
        raise
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            close_on_return = True  # Connection may be broken
        logger.error(f"Database error: {exc}")
        raise
    finally:
        db_pool.return_connection(conn, close=close_on_return)


@contextmanager
def get_db_cursor(cursor_factory=None, read_only=False):
    """
    Context manager for database cursor using connection pool.

    PERFORMANCE FIX: Now uses connection pool instead of creating new
    connections for every single query. This reduces connection overhead
    from ~100ms per query to <1ms.

    Usage:
        with get_db_cursor() as cursor:
            cursor.execute("SELECT ...")
            results = cursor.fetchall()
    """
    close_on_return = False
    conn = None
    cursor = None

    try:
        # Use the connection pool for better performance
        conn = db_pool.get_connection()

        cursor = conn.cursor(cursor_factory=cursor_factory)
        try:
            yield cursor
            if read_only:
                # Roll back read-only transactions to avoid unnecessary
                # COMMIT round-trips.
                conn.rollback()
            else:
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
                if cursor is not None:
                    cursor.close()
            except Exception:
                # Best-effort cleanup; don't let cleanup issues mask original errors
                pass
    finally:
        # Always return connection to pool
        if conn is not None:
            try:
                db_pool.return_connection(conn, close=close_on_return)
            except Exception:
                try:
                    conn.close()
                except Exception:
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
        """Execute a query for many parameter sets efficiently."""
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
        """Get all resources for a user using the normalized Economy 2.0 schema"""
        query = """
            SELECT rd.name, COALESCE(ue.quantity, 0) AS quantity
            FROM resource_dictionary rd
            LEFT JOIN user_economy ue
                ON ue.resource_id = rd.resource_id AND ue.user_id = %s
            WHERE rd.is_active = TRUE
        """
        rows = QueryHelper.fetch_all(query, (user_id,), dict_cursor=True)
        return {row["name"]: int(row["quantity"]) for row in rows} if rows else {}

    @staticmethod
    def get_user_military(user_id: int) -> Dict[str, int]:
        """Get all military units for a user using the normalized schema.

        Returns a dict like {'soldiers': 100, 'tanks': 5, ...} with
        every unit from unit_dictionary represented (0 when absent).
        Also includes 'default_defense' from the stats table.
        """
        # Unit quantities from user_military + unit_dictionary
        unit_query = """
            SELECT ud.name, COALESCE(um.quantity, 0) AS quantity
            FROM unit_dictionary ud
            LEFT JOIN user_military um
                ON um.unit_id = ud.unit_id AND um.user_id = %s
            WHERE ud.is_active = TRUE
        """
        rows = QueryHelper.fetch_all(unit_query, (user_id,), dict_cursor=True)
        result: Dict[str, int] = {row["name"]: int(row["quantity"]) for row in rows}

        # Supplement with stats-level fields
        stats_query = "SELECT manpower, default_defense FROM stats WHERE id = %s"
        stats_row = QueryHelper.fetch_one(stats_query, (user_id,), dict_cursor=True)
        if stats_row:
            result["manpower"] = int(stats_row.get("manpower", 0) or 0)
            result["default_defense"] = stats_row.get("default_defense", "")
        else:
            result["manpower"] = 0
            result["default_defense"] = ""

        return result

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
        """Get all provinces with their building counts using normalized schema."""
        query = """
            SELECT
                p.id, p.provinceName, p.population, p.land, p.cityCount,
                p.energy, p.happiness, p.pollution, p.productivity, p.consumer_spending,
                bd.name AS building_name, COALESCE(ub.quantity, 0) AS quantity
            FROM provinces p
            LEFT JOIN user_buildings ub ON ub.user_id = p.userId
            LEFT JOIN building_dictionary bd
                ON bd.building_id = ub.building_id
                AND bd.is_active = TRUE
            WHERE p.userId = %s
            ORDER BY p.id, bd.name
        """
        results = QueryHelper.fetch_all(query, (user_id,), dict_cursor=True)
        # Group by province
        provinces = {}
        for row in results:
            pid = row["id"]
            if pid not in provinces:
                provinces[pid] = {
                    "id": pid,
                    "provinceName": row["provincename"],
                    "population": row["population"],
                    "land": row["land"],
                    "cityCount": row["citycount"],
                    "energy": row["energy"],
                    "happiness": row["happiness"],
                    "pollution": row["pollution"],
                    "productivity": row["productivity"],
                    "consumer_spending": row["consumer_spending"],
                    "buildings": {},
                }
            bname = row.get("building_name")
            if bname:
                provinces[pid]["buildings"][bname] = row["quantity"]
        return list(provinces.values())

    @staticmethod
    def get_province_ids_by_user(user_id: int) -> List[int]:
        """Get all province IDs for a user efficiently"""
        query = "SELECT id FROM provinces WHERE userId = %s ORDER BY id"
        results = QueryHelper.fetch_all(query, (user_id,))
        return [row[0] for row in results]

    @staticmethod
    def get_total_infrastructure_by_user(user_id: int) -> Dict[str, int]:
        """Get total building counts for a user using normalized schema."""
        query = """
            SELECT bd.name, COALESCE(SUM(ub.quantity), 0) AS total
            FROM building_dictionary bd
            LEFT JOIN user_buildings ub
                ON ub.building_id = bd.building_id AND ub.user_id = %s
            WHERE bd.is_active = TRUE
            GROUP BY bd.name
        """
        results = QueryHelper.fetch_all(query, (user_id,), dict_cursor=True)
        return {row["name"]: int(row["total"]) for row in results}


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
        # Pre-aggregate core influence metrics (military/resources scoring to be added)
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
    def batch_update_resources(
        user_resources: List[Tuple[int, str, int]],
    ) -> None:
        """Batch update resources using normalized Economy 2.0 schema.

        Args:
            user_resources: List of (user_id, resource_name, amount)
        """
        if not user_resources:
            return

        # Resolve resource names to resource_ids once
        distinct_names = list({name for _, name, _ in user_resources})
        name_query = (
            "SELECT resource_id, name FROM resource_dictionary WHERE name = ANY(%s)"
        )
        rows = QueryHelper.fetch_all(name_query, (distinct_names,), dict_cursor=True)
        name_to_id = {row["name"]: row["resource_id"] for row in rows}

        # Build upsert values: (user_id, resource_id, amount)
        upsert_values = []
        affected_user_ids = set()
        for user_id, resource_name, amount in user_resources:
            resource_id = name_to_id.get(resource_name)
            if resource_id is None:
                continue
            upsert_values.append((user_id, resource_id, amount))
            affected_user_ids.add(user_id)

        if upsert_values:
            upsert_query = """
                INSERT INTO user_economy (user_id, resource_id, quantity)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, resource_id)
                DO UPDATE SET
                    quantity = GREATEST(
                        user_economy.quantity + EXCLUDED.quantity, 0
                    )
            """
            QueryHelper.execute_many(upsert_query, upsert_values)

        # Invalidate caches for all affected users so future reads are fresh
        try:
            for uid in affected_user_ids:
                invalidate_user_cache(uid)
        except Exception:
            # Cache invalidation should not raise from batch operation
            pass

    @staticmethod
    def batch_update_military(user_units: List[Tuple[int, str, int]]) -> None:
        """
        Batch update military units for multiple users using the normalized schema.

        Args:
            user_units: List of tuples (user_id, unit_name, amount)
        """
        if not user_units:
            return

        # Resolve unit names to unit_ids once
        distinct_names = list({name for _, name, _ in user_units})
        name_query = "SELECT unit_id, name FROM unit_dictionary WHERE name = ANY(%s)"
        rows = QueryHelper.fetch_all(name_query, (distinct_names,), dict_cursor=True)
        name_to_id = {row["name"]: row["unit_id"] for row in rows}

        # Build upsert values: (user_id, unit_id, amount)
        upsert_values = []
        affected_user_ids = set()
        for user_id, unit_name, amount in user_units:
            unit_id = name_to_id.get(unit_name)
            if unit_id is None:
                continue
            upsert_values.append((user_id, unit_id, amount))
            affected_user_ids.add(user_id)

        if upsert_values:
            upsert_query = """
                INSERT INTO user_military (user_id, unit_id, quantity, updated_at)
                VALUES (%s, %s, %s, now())
                ON CONFLICT (user_id, unit_id)
                DO UPDATE SET
                    quantity = GREATEST(
                        user_military.quantity + EXCLUDED.quantity, 0
                    ),
                    updated_at = now()
            """
            QueryHelper.execute_many(upsert_query, upsert_values)

        try:
            for uid in affected_user_ids:
                invalidate_user_cache(uid)
        except Exception:
            pass


# Utility functions for common operations
def get_user_full_data(user_id: int) -> Dict[str, Any]:
    """Get all user data in optimized queries"""
    return {
        "resources": UserQueries.get_user_resources(user_id),
        "military": UserQueries.get_user_military(user_id),
        "stats": UserQueries.get_user_stats(user_id),
        "provinces": ProvinceQueries.get_user_provinces_summary(user_id),
    }


# ---------------------------------------------------------------------------
# Request-scoped connection: one pool checkout per HTTP request
# ---------------------------------------------------------------------------


def get_request_connection():
    """Return (and lazily create) a DB connection scoped to the current
    Flask request.  Stored on ``flask.g`` so every ``get_request_cursor()``
    call within the same request reuses the same connection — eliminating
    the ~130 ms Railway proxy overhead for each additional cursor.

    The connection is returned to the pool automatically by
    ``teardown_request_connection()`` (registered in app.py).
    """
    from flask import g

    conn = getattr(g, "_db_conn", None)
    if conn is None or getattr(conn, "closed", 1):
        conn = db_pool.get_connection()
        g._db_conn = conn
    return conn


@contextmanager
def get_request_cursor(cursor_factory=None, read_only=False):
    """Like ``get_db_cursor`` but reuses the request-scoped connection.

    *   First call in a request checks out a connection from the pool
        (~130 ms through Railway proxy).
    *   Every subsequent call in the SAME request costs only the cursor
        creation (~0 ms).

    The cursor is closed when the context manager exits.  The connection
    itself is committed/returned by ``teardown_request_connection``.
    """
    conn = get_request_connection()
    cursor = conn.cursor(cursor_factory=cursor_factory)
    try:
        yield cursor
    except (psycopg2.InterfaceError, psycopg2.OperationalError):
        # Mark conn as broken so teardown closes instead of returning it
        from flask import g

        g._db_conn_broken = True
        raise
    except Exception:
        raise
    finally:
        try:
            cursor.close()
        except Exception:
            pass


def teardown_request_connection(exc=None):
    """Return the request-scoped connection to the pool.

    Call this from ``app.teardown_appcontext`` in app.py::

        app.teardown_appcontext(teardown_request_connection)
    """
    from flask import g

    conn = getattr(g, "_db_conn", None)
    if conn is None:
        return

    broken = getattr(g, "_db_conn_broken", False)
    try:
        if broken or exc is not None:
            try:
                conn.rollback()
            except Exception:
                pass
            db_pool.return_connection(conn, close=broken)
        else:
            try:
                conn.commit()
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                db_pool.return_connection(conn, close=True)
                return
            db_pool.return_connection(conn)
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
    finally:
        g._db_conn = None
        g._db_conn_broken = False


@contextmanager
def reuse_or_new_cursor(existing_cursor=None, cursor_factory=None, read_only=False):
    """Context manager that reuses an existing DB cursor or creates a new one.

    This avoids opening a new connection from the pool (which costs ~130ms
    in network round-trip to the Railway Postgres proxy) when the caller
    already has a cursor open.

    When *cursor_factory* is specified and the existing cursor is of a
    different type (e.g. the caller needs a RealDictCursor but the parent
    cursor returns tuples), a **new cursor is opened on the same
    connection** — this avoids a pool checkout while still returning the
    right row type.

    Usage:
        with reuse_or_new_cursor(parent_cursor) as db:
            db.execute("SELECT ...")
    """
    if existing_cursor is not None:
        # Check whether the caller needs a different cursor type
        need_different_factory = cursor_factory is not None and not isinstance(
            existing_cursor, cursor_factory
        )
        if need_different_factory:
            # Open a new cursor on the SAME connection (no pool checkout)
            new_cur = existing_cursor.connection.cursor(cursor_factory=cursor_factory)
            try:
                yield new_cur
            finally:
                new_cur.close()
        else:
            yield existing_cursor
    else:
        # No cursor provided — open a new one as usual
        with get_db_cursor(
            cursor_factory=cursor_factory, read_only=read_only
        ) as new_cursor:
            yield new_cursor


def close_database_pool():
    """Close all database connections (call on application shutdown)"""
    db_pool.close_all()
