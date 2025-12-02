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

load_dotenv()

logger = logging.getLogger(__name__)


class DatabasePool:
    """Singleton database connection pool"""
    _instance = None
    _pool = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabasePool, cls).__new__(cls)
            cls._instance._initialize_pool()
        return cls._instance

    def _initialize_pool(self):
        """Initialize the connection pool"""
        try:
            self._pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=20,
                database=os.getenv("PG_DATABASE"),
                user=os.getenv("PG_USER"),
                password=os.getenv("PG_PASSWORD"),
                host=os.getenv("PG_HOST"),
                port=os.getenv("PG_PORT")
            )
            logger.info("Database connection pool initialized")
        except Exception as e:
            logger.error(f"Failed to initialize database pool: {e}")
            raise

    def get_connection(self):
        """Get a connection from the pool"""
        return self._pool.getconn()

    def return_connection(self, conn):
        """Return a connection to the pool"""
        self._pool.putconn(conn)

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
        conn.rollback()
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
    conn = db_pool.get_connection()
    cursor = conn.cursor(cursor_factory=cursor_factory)
    try:
        yield cursor
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        cursor.close()
        db_pool.return_connection(conn)


class QueryHelper:
    """Helper class for common database queries"""

    @staticmethod
    def fetch_one(query: str, params: tuple = None, dict_cursor: bool = False) -> Optional[Any]:
        """Execute a query and fetch one result"""
        cursor_factory = RealDictCursor if dict_cursor else None
        with get_db_cursor(cursor_factory=cursor_factory) as cursor:
            cursor.execute(query, params)
            return cursor.fetchone()

    @staticmethod
    def fetch_all(query: str, params: tuple = None, dict_cursor: bool = False) -> List[Any]:
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
        return {'gold': result[0]} if result else {'gold': 0}

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
        'resources': UserQueries.get_user_resources(user_id),
        'military': UserQueries.get_user_military(user_id),
        'stats': UserQueries.get_user_stats(user_id),
        'provinces': ProvinceQueries.get_user_provinces_summary(user_id)
    }


def close_database_pool():
    """Close all database connections (call on application shutdown)"""
    db_pool.close_all()
