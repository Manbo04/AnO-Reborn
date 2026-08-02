from celery import Celery
import psycopg2
import os
import time
import logging
from dotenv import load_dotenv
from attack_scripts import Economy
import math
from celery.schedules import crontab
import variables
import redis

logger = logging.getLogger(__name__)

load_dotenv()
import config  # Parse Railway environment variables  # noqa: E402

# Toggle noisy per-building revenue logs (default off in production)
VERBOSE_REVENUE_LOGS = os.getenv("VERBOSE_REVENUE_LOGS") == "1"

from app_core.celery_schedule import CELERY_BEAT_SCHEDULE, TASK_RUN_THRESHOLDS

# Mapping from normalized building names to produced resource names.
# Used by the global tick economy engine.
# NOTE: BUILDING_PRODUCTION_RESOURCE_MAP was removed.  These buildings are
# now handled exclusively by generate_province_revenue() (hourly) which
# enforces energy, gold upkeep, and input-resource checks.  Having them
# here too caused DOUBLE production and free resources (steel mills
# produced steel without consuming coal/iron, etc.).
BUILDING_PRODUCTION_RESOURCE_MAP = {}


redis_url = config.get_redis_url()
celery = Celery("app", broker=redis_url)
celery.conf.update(
    broker_url=redis_url, result_backend=redis_url, CELERY_BROKER_URL=redis_url
)

celery.conf.update(
    timezone="UTC",
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    beat_schedule=CELERY_BEAT_SCHEDULE,
)


# Centralized helper for last_run threshold check



# Returns how many rations a player needs
# (matching population_growth consumption logic)
def rations_needed(cId, db=None):
    from database import reuse_or_new_cursor, row_val

    with reuse_or_new_cursor(db) as active_db:
        # Check if Rationing Program policy is enabled
        active_db.execute(
            "SELECT education FROM policies WHERE user_id = %s",
            (cId,),
        )
        policy_row = active_db.fetchone()
        policies = row_val(policy_row, "education", 0, default=[]) or []

        rationing_multiplier = (
            variables.POLICY_RATIONING_CONSUMPTION_REDUCTION
            if variables.POLICY_RATIONING_PROGRAM in policies
            else 1.0
        )

        pw_mult = variables.DEMO_RATIONS_CONSUMPTION["pop_working"]
        pc_mult = variables.DEMO_RATIONS_CONSUMPTION["pop_children"]
        pe_mult = variables.DEMO_RATIONS_CONSUMPTION["pop_elderly"]
        r_per = variables.RATIONS_PER

        if variables.FEATURE_DEMOGRAPHIC_CONSUMPTION:
            query = f"""
                SELECT COALESCE(SUM(
                    GREATEST(
                        CAST(
                            CASE WHEN pop_children IS NOT NULL THEN
                                (COALESCE(pop_working,0) * {pw_mult} + COALESCE(pop_children,0) * {pc_mult} + COALESCE(pop_elderly,0) * {pe_mult}) * {rationing_multiplier}
                            ELSE
                                FLOOR(COALESCE(population,0) / {r_per}) * {rationing_multiplier}
                            END
                        AS INTEGER),
                        1
                    )
                ), 0)
                FROM provinces WHERE userId = %s
            """
        else:
            query = f"""
                SELECT COALESCE(SUM(
                    GREATEST(
                        CAST(
                            FLOOR(COALESCE(population,0) / {r_per}) * {rationing_multiplier}
                        AS INTEGER),
                        1
                    )
                ), 0)
                FROM provinces WHERE userId = %s
            """
        
        active_db.execute(query, (cId,))
        total_needed = active_db.fetchone()
        ans = int(total_needed[0]) if total_needed and total_needed[0] else 0
        return ans if ans > 0 else 1




def rations_distribution_capacity(user_id):
    """Return the population that can be served by distribution buildings."""
    if not variables.FEATURE_RATIONS_DISTRIBUTION:
        return None

    from database import get_db_cursor

    with get_db_cursor() as db:
        # Query normalized user_buildings table — tiered capacity per building type
        db.execute(
            """
            SELECT bd.name, COALESCE(SUM(ub.quantity), 0) AS qty
            FROM user_buildings ub
            JOIN building_dictionary bd
                ON bd.building_id = ub.building_id
            WHERE ub.user_id = %s
              AND bd.name IN (
                  'distribution_centers', 'food_banks', 'gas_stations', 'general_stores',
                  'farmers_markets', 'malls'
              )
            GROUP BY bd.name
            """,
            (user_id,),
        )
        total = 0
        for row in db.fetchall():
            bname = row[0]
            qty = row[1] or 0
            cap = variables.RATIONS_DISTRIBUTION_PER_BUILDING.get(
                bname, variables.RATIONS_DISTRIBUTION_PER_BUILDING_DEFAULT
            )
            total += qty * cap
    return total




# Returns a rations score for a user, from -1 to -1.4
# -1 = Enough or more than enough rations
# -1.4 = No rations at all
def food_stats(user_id, db=None):
    from database import reuse_or_new_cursor, row_val

    with reuse_or_new_cursor(db) as active_db:
        needed_rations = rations_needed(user_id, db=active_db)

        # Query normalized user_economy table
        active_db.execute(
            """
            SELECT COALESCE(ue.quantity, 0)
            FROM user_economy ue
            JOIN resource_dictionary rd ON rd.resource_id = ue.resource_id
            WHERE ue.user_id = %s AND rd.name = 'rations'
            """,
            (user_id,),
        )
        row = active_db.fetchone()
        current_rations = row_val(row, "coalesce", 0, default=0) or 0

        # compute distribution capacity if the feature is enabled
        distribution_cap = None
        if variables.FEATURE_RATIONS_DISTRIBUTION:
            # Query normalized user_buildings table — tiered capacity
            active_db.execute(
                """
                SELECT bd.name, COALESCE(SUM(ub.quantity), 0) AS qty
                FROM user_buildings ub
                JOIN building_dictionary bd ON bd.building_id = ub.building_id
                WHERE ub.user_id = %s
                  AND bd.name IN ('distribution_centers', 'food_banks', 'gas_stations',
                                  'general_stores', 'farmers_markets', 'malls')
                GROUP BY bd.name
                """,
                (user_id,),
            )
            distribution_cap = 0
            for brow in active_db.fetchall():
                bname = row_val(brow, "name", 0)
                qty = row_val(brow, "qty", 1, default=0) or 0
                cap = variables.RATIONS_DISTRIBUTION_PER_BUILDING.get(
                    bname, variables.RATIONS_DISTRIBUTION_PER_BUILDING_DEFAULT
                )
                distribution_cap += qty * cap

    if needed_rations == 0:
        needed_rations = 1

    # If the new feature is active, only rations covered by distribution
    # buildings count towards the effective supply.
    if distribution_cap is not None:
        effective_rations = min(current_rations, distribution_cap)
    else:
        effective_rations = current_rations

    rcp = (effective_rations / needed_rations) - 1  # Normalizes the score to 0.
    if rcp > 0:
        rcp = 0

    score = -1 + (rcp * variables.NO_FOOD_TAX_MULTIPLIER)

    return score




def compute_rations_distribution_cap(building_qty_by_name):
    """Sum population served by distribution buildings (pure helper for UI/tests)."""
    total = 0
    for bname, qty in (building_qty_by_name or {}).items():
        if bname not in variables.RATIONS_DISTRIBUTION_BUILDINGS:
            continue
        per_building = variables.RATIONS_DISTRIBUTION_PER_BUILDING.get(
            bname, variables.RATIONS_DISTRIBUTION_PER_BUILDING_DEFAULT
        )
        total += int(qty or 0) * per_building
    return total




def nation_distribution_status(
    total_population,
    rations_stockpile,
    rations_need,
    building_qty_by_name,
):
    """Build template-friendly distribution summary (no DB)."""
    if not variables.FEATURE_RATIONS_DISTRIBUTION:
        return None

    cap = compute_rations_distribution_cap(building_qty_by_name)
    pop = int(total_population or 0)
    need = max(int(rations_need or 0), 1)
    stock = int(rations_stockpile or 0)
    uncovered = max(0, pop - cap)
    coverage_pct = min(100, int(100 * cap / pop)) if pop > 0 else 100
    dc_cap = variables.RATIONS_DISTRIBUTION_PER_BUILDING["food_banks"]
    dc_suggested = (uncovered + dc_cap - 1) // dc_cap if uncovered > 0 else 0
    stockpile_bottleneck = stock >= need and cap < pop
    return {
        "distribution_cap": cap,
        "rations_stockpile": stock,
        "uncovered_population": uncovered,
        "coverage_percent": coverage_pct,
        "distribution_centers_suggested": dc_suggested,
        "stockpile_bottleneck": stockpile_bottleneck,
        "show_alert": cap < pop and stock > 0,
    }




def fetch_nation_distribution_status(db, user_id, total_population, rations_need):
    """Load economy/buildings and return nation_distribution_status dict."""
    from database import row_val

    if not variables.FEATURE_RATIONS_DISTRIBUTION:
        return None

    db.execute(
        """
        SELECT COALESCE(ue.quantity, 0)
        FROM user_economy ue
        JOIN resource_dictionary rd ON rd.resource_id = ue.resource_id
        WHERE ue.user_id = %s AND rd.name = 'rations'
        """,
        (user_id,),
    )
    row = db.fetchone()
    rations_stockpile = int(row_val(row, "coalesce", 0, default=0) or 0)

    db.execute(
        """
        SELECT bd.name, COALESCE(SUM(ub.quantity), 0) AS qty
        FROM user_buildings ub
        JOIN building_dictionary bd ON bd.building_id = ub.building_id
        WHERE ub.user_id = %s
          AND bd.name = ANY(%s)
        GROUP BY bd.name
        """,
        (user_id, list(variables.RATIONS_DISTRIBUTION_BUILDINGS)),
    )
    building_qty = {
        row_val(r, "name", 0): int(row_val(r, "qty", 1, default=0) or 0)
        for r in db.fetchall()
    }
    db.execute("SELECT land FROM provinces WHERE userId = %s", (user_id,))
    user_provinces = db.fetchall()
    total_land = sum((int(row_val(r, "land", 0, default=0) or 0) for r in user_provinces)) if user_provinces else 0
    grace_period = (len(user_provinces) <= 1) and (total_land <= 20)
    
    status = nation_distribution_status(
        total_population, rations_stockpile, rations_need, building_qty
    )
    if status:
        status["grace_period"] = grace_period
    return status




def consumer_goods_distribution_capacity(user_id, db=None):
    """Return the population that can be served by CG distribution buildings."""
    if not variables.FEATURE_DEMOGRAPHIC_CONSUMPTION:
        return None

    from database import reuse_or_new_cursor, row_val

    with reuse_or_new_cursor(db) as active_db:
        # Query normalized user_buildings table — tiered CG capacity
        active_db.execute(
            """
            SELECT bd.name, COALESCE(SUM(ub.quantity), 0) AS qty
            FROM user_buildings ub
            JOIN building_dictionary bd
                ON bd.building_id = ub.building_id
            WHERE ub.user_id = %s
              AND bd.name IN (
                  'distribution_centers', 'food_banks', 'malls',
                  'general_stores', 'gas_stations'
              )
            GROUP BY bd.name
            """,
            (user_id,),
        )
        total = 0
        for row in active_db.fetchall():
            bname = row_val(row, "name", 0)
            qty = row_val(row, "qty", 1, default=0) or 0
            cap = variables.CONSUMER_GOODS_DISTRIBUTION_PER_BUILDING.get(
                bname, variables.CONSUMER_GOODS_DISTRIBUTION_PER_BUILDING_DEFAULT
            )
            total += qty * cap
    return total




def calculate_demographic_rations_need(province_id):
    """
    Calculate rations needed for a province based on demographic brackets.

    Returns: (rations_needed, shortage_risk)
    where shortage_risk is True if distribution is limited
    """
    if not variables.FEATURE_DEMOGRAPHIC_CONSUMPTION:
        return None

    from database import get_db_cursor

    with get_db_cursor() as db:
        # Fetch demographic data
        db.execute(
            """
            SELECT pop_children, pop_working, pop_elderly, userId
            FROM provinces
            WHERE id = %s
            """,
            (province_id,),
        )
        row = db.fetchone()
        if not row:
            return 0, 0, False

        pop_children, pop_working, pop_elderly, user_id = row

        # Check if Rationing Program policy is enabled
        db.execute(
            "SELECT education FROM policies WHERE user_id = %s",
            (user_id,),
        )
        policy_row = db.fetchone()
        policies = policy_row[0] if policy_row else []

        # Apply rationing multiplier to consumption
        rationing_multiplier = (
            variables.POLICY_RATIONING_CONSUMPTION_REDUCTION
            if variables.POLICY_RATIONING_PROGRAM in policies
            else 1.0
        )

        # Calculate baseline rations need using demographic rates
        rations_needed = 0
        rations_needed += (
            pop_working
            * variables.DEMO_RATIONS_CONSUMPTION["pop_working"]
            * rationing_multiplier
        )
        rations_needed += (
            pop_children
            * variables.DEMO_RATIONS_CONSUMPTION["pop_children"]
            * rationing_multiplier
        )
        rations_needed += (
            pop_elderly
            * variables.DEMO_RATIONS_CONSUMPTION["pop_elderly"]
            * rationing_multiplier
        )

        # Get distribution capacity (user-level)
        dist_capacity = rations_distribution_capacity(user_id)
        shortage_risk = dist_capacity is not None and dist_capacity < (
            pop_children + pop_working + pop_elderly
        )

        return int(rations_needed), dist_capacity, shortage_risk




def calculate_demographic_consumer_goods_need(province_id):
    """
    Calculate CG needed for a province based on demographic brackets.

    Returns: (cg_needed, distribution_capacity, bottlenecked)
    where bottlenecked is True if CG distribution is limited
    """
    if not variables.FEATURE_DEMOGRAPHIC_CONSUMPTION:
        return None

    from database import get_db_cursor

    with get_db_cursor() as db:
        # Fetch demographic data
        db.execute(
            """
            SELECT pop_children, pop_working, pop_elderly, userId
            FROM provinces
            WHERE id = %s
            """,
            (province_id,),
        )
        row = db.fetchone()
        if not row:
            return 0, None, False

        pop_children, pop_working, pop_elderly, user_id = row

        # Check if Universal Healthcare policy is enabled
        db.execute(
            "SELECT education FROM policies WHERE user_id = %s",
            (user_id,),
        )
        policy_row = db.fetchone()
        policies = policy_row[0] if policy_row else []

        # Apply healthcare multiplier to elderly CG consumption
        elderly_cg_multiplier = (
            variables.POLICY_HEALTHCARE_ELDERLY_CG_MULTIPLIER
            if variables.POLICY_UNIVERSAL_HEALTHCARE in policies
            else 1.0
        )

        # Calculate baseline CG need using demographic rates
        cg_needed = 0
        cg_needed += (
            pop_working * variables.DEMO_CONSUMER_GOODS_CONSUMPTION["pop_working"]
        )
        cg_needed += (
            pop_children * variables.DEMO_CONSUMER_GOODS_CONSUMPTION["pop_children"]
        )
        cg_needed += (
            pop_elderly
            * variables.DEMO_CONSUMER_GOODS_CONSUMPTION["pop_elderly"]
            * elderly_cg_multiplier
        )

        # Get distribution capacity (user-level)
        dist_capacity = consumer_goods_distribution_capacity(user_id)

        # Determine if bottleneck exists
        total_population = pop_children + pop_working + pop_elderly
        bottlenecked = dist_capacity is not None and dist_capacity < total_population

        return int(cg_needed), dist_capacity, bottlenecked


