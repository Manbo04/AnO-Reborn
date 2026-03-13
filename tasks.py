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
import urllib.parse

logger = logging.getLogger(__name__)

load_dotenv()
import config  # Parse Railway environment variables  # noqa: E402

# Toggle noisy per-building revenue logs (default off in production)
VERBOSE_REVENUE_LOGS = os.getenv("VERBOSE_REVENUE_LOGS") == "1"

# Configurable task timing thresholds (seconds)
TASK_RUN_THRESHOLDS = {
    "tax_income": int(os.getenv("TAX_INCOME_MIN_INTERVAL", "65")),
    "population_growth": int(os.getenv("POP_GROWTH_MIN_INTERVAL", "100")),
    "generate_province_revenue": int(os.getenv("PROV_REV_MIN_INTERVAL", "100")),
    "execute_trade_agreements": int(os.getenv("TRADE_AGR_MIN_INTERVAL", "65")),
    "global_tick": int(os.getenv("GLOBAL_TICK_MIN_INTERVAL", "540")),
}

# Mapping from normalized building names to produced resource names.
# Used by the global tick economy engine.
# NOTE: BUILDING_PRODUCTION_RESOURCE_MAP was removed.  These buildings are
# now handled exclusively by generate_province_revenue() (hourly) which
# enforces energy, gold upkeep, and input-resource checks.  Having them
# here too caused DOUBLE production and free resources (steel mills
# produced steel without consuming coal/iron, etc.).
BUILDING_PRODUCTION_RESOURCE_MAP = {}


# Optionally allow celery beat schedule to be loaded from env/config
def get_crontab_env(var, default):
    val = os.getenv(var)
    if val:
        # Support formats like "0" or "*/15" or "5,35"
        return crontab(minute=val)
    return default


redis_url = config.get_redis_url()
celery = Celery("app", broker=redis_url)
celery.conf.update(
    broker_url=redis_url, result_backend=redis_url, CELERY_BROKER_URL=redis_url
)

# Allow schedule override via env, fallback to defaults
celery_beat_schedule = {
    "tax_income": {
        "task": "tasks.task_tax_income",
        "schedule": get_crontab_env("TAX_INCOME_CRON", crontab(minute="0")),
    },
    "generate_province_revenue": {
        "task": "tasks.task_generate_province_revenue",
        "schedule": get_crontab_env("PROV_REV_CRON", crontab(minute="25")),
    },
    "population_growth": {
        "task": "tasks.task_population_growth",
        "schedule": get_crontab_env("POP_GROWTH_CRON", crontab(minute="45")),
    },
    "war_reparation_tax": {
        "task": "tasks.task_war_reparation_tax",
        "schedule": get_crontab_env("WAR_REP_CRON", crontab(minute="0", hour="0")),
    },
    "manpower_increase": {
        "task": "tasks.task_manpower_increase",
        "schedule": get_crontab_env("MANPOWER_CRON", crontab(minute="5", hour="*/4")),
    },
    "backfill_missing_resources": {
        "task": "tasks.task_backfill_missing_resources",
        "schedule": get_crontab_env("BACKFILL_CRON", crontab(minute="15", hour="1")),
    },
    "cleanup_orphan_user_rows": {
        "task": "tasks.task_cleanup_orphan_user_rows",
        "schedule": get_crontab_env(
            "ORPHAN_CLEANUP_CRON", crontab(minute="10", hour="1")
        ),
    },
    "refresh_bot_offers": {
        "task": "tasks.task_refresh_bot_offers",
        "schedule": get_crontab_env("BOT_OFFERS_CRON", crontab(minute="*/5")),
    },
    "execute_trade_agreements": {
        "task": "tasks.task_execute_trade_agreements",
        "schedule": get_crontab_env("TRADE_AGR_CRON", crontab(minute="*/15")),
    },
    "global_tick": {
        "task": "tasks.task_global_tick",
        "schedule": get_crontab_env("GLOBAL_TICK_CRON", crontab(minute="*/10")),
    },
    "cleanup_old_spyinfo": {
        "task": "tasks.task_cleanup_old_spyinfo",
        "schedule": get_crontab_env(
            "SPYINFO_CLEANUP_CRON", crontab(minute="30", hour="2")
        ),
    },
    "economy_snapshot": {
        "task": "tasks.task_economy_snapshot",
        "schedule": get_crontab_env(
            "ECONOMY_SNAPSHOT_CRON", crontab(minute="0", hour="*/1")
        ),
    },
}

celery.conf.update(
    timezone="UTC",
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    beat_schedule=celery_beat_schedule,
)


# Centralized helper for last_run threshold check
def should_skip_task(row, task_name):
    import datetime

    now = datetime.datetime.now(datetime.timezone.utc)
    threshold = TASK_RUN_THRESHOLDS.get(task_name, 90)
    if row and row[0] and (now - row[0]).total_seconds() < threshold:
        print(f"{task_name}: last run too recent, skipping (interval={threshold}s)")
        return True
    return False


def is_task_stale(task_name: str, stale_seconds: int) -> bool:
    """Return True if a task has not run within stale_seconds.

    This is used as a safety net for scheduler drift/failures so critical
    economy tasks can be self-healed by other periodic tasks.
    """
    from database import get_db_connection
    import datetime

    now = datetime.datetime.now(datetime.timezone.utc)
    try:
        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS task_runs (
                    task_name TEXT PRIMARY KEY,
                    last_run TIMESTAMP WITH TIME ZONE
                )
                """
            )
            db.execute(
                "SELECT last_run FROM task_runs WHERE task_name=%s",
                (task_name,),
            )
            row = db.fetchone()
            if not row or not row[0]:
                return True
            age_seconds = (now - row[0]).total_seconds()
            return age_seconds > stale_seconds
    except Exception:
        # Fail-open so watchdog callers can attempt a recovery run.
        return True


# Handles exception for an error
def handle_exception(e):
    filename = __file__
    line = e.__traceback__.tb_lineno
    print("\n-----------------START OF EXCEPTION-------------------")
    print(f"Filename: {filename}")
    print(f"Error: {e}")
    print(f"Line: {line}")
    print("-----------------END OF EXCEPTION---------------------\n")


def log_verbose(message: str):
    """Emit detailed logs only when enabled."""
    if VERBOSE_REVENUE_LOGS:
        print(message)


# Maximum 32-bit signed integer to guard against overflow when writing to DB
MAX_INT_32 = 2_147_483_647


def _safe_update_productivity(db, province_id, multiplier):
    """Read the current productivity, apply a multiplier and write back while
    clamping to 32-bit signed integer limits. This prevents DB errors when
    intermediate computations overflow Python int ranges expected by downstream
    databases or drivers in tests."""
    db.execute("SELECT productivity FROM provinces WHERE id=%s", (province_id,))
    row = db.fetchone()
    current = row[0] if row and row[0] is not None else 0
    try:
        new_val = int(round(current * multiplier))
    except Exception:
        new_val = int(current)
    if new_val > MAX_INT_32:
        new_val = MAX_INT_32
    db.execute(
        "UPDATE provinces SET productivity=%s WHERE id=%s", (new_val, province_id)
    )


def try_pg_advisory_lock(conn, lock_id: int, label: str) -> bool:
    """Attempt a transaction-level advisory lock.

    Uses pg_try_advisory_xact_lock so the lock is automatically released
    when the transaction ends (COMMIT or ROLLBACK), eliminating the risk
    of stale session-level locks blocking all future runs if a task
    crashes without explicit cleanup.
    """
    try:
        cur = conn.cursor()
        cur.execute("SELECT pg_try_advisory_xact_lock(%s)", (lock_id,))
        row = cur.fetchone()
        if not row:
            # In some test fakes, fetchone() may return None; allow tasks
            # to proceed while logging a warning.
            print(
                f"{label}: advisory lock query returned no rows " "- proceeding anyway"
            )
            return True
        acquired = row[0]
        if not acquired:
            print(f"{label}: another run is already in progress, " "skipping")
        return acquired
    except Exception as e:
        print(f"{label}: failed to acquire advisory lock: {e}")
        return False


def release_pg_advisory_lock(conn, lock_id: int):
    """No-op kept for backward compatibility.

    Transaction-level advisory locks (pg_try_advisory_xact_lock) are
    released automatically on COMMIT / ROLLBACK, so explicit unlocks
    are no longer needed.  Callers that still invoke this function
    will simply succeed harmlessly.
    """
    pass


# Returns how many rations a player needs
# (matching population_growth consumption logic)
def rations_needed(cId):
    from database import get_db_cursor

    with get_db_cursor() as db:
        # Check if Rationing Program policy is enabled
        db.execute(
            "SELECT education FROM policies WHERE user_id = %s",
            (cId,),
        )
        policy_row = db.fetchone()
        policies = policy_row[0] if policy_row else []

        rationing_multiplier = (
            variables.POLICY_RATIONING_CONSUMPTION_REDUCTION
            if variables.POLICY_RATIONING_PROGRAM in policies
            else 1.0
        )

        # Get population per province - each province has minimum 1 ration
        db.execute(
            (
                "SELECT population, pop_children, pop_working, "
                "pop_elderly FROM provinces WHERE userId=%s"
            ),
            (cId,),
        )
        provinces = db.fetchall()

        total_needed = 0
        for province_row in provinces:
            if (
                variables.FEATURE_DEMOGRAPHIC_CONSUMPTION
                and len(province_row) >= 4
                and province_row[1] is not None
            ):
                # Demographic-based: pop_children, pop_working, pop_elderly
                pop, pc, pw, pe = province_row
                province_consumption = int(
                    (
                        pw * variables.DEMO_RATIONS_CONSUMPTION["pop_working"]
                        + pc * variables.DEMO_RATIONS_CONSUMPTION["pop_children"]
                        + pe * variables.DEMO_RATIONS_CONSUMPTION["pop_elderly"]
                    )
                    * rationing_multiplier
                )
            else:
                # Fallback to old method: total population / RATIONS_PER
                pop = province_row[0] if province_row else 0
                province_pop = pop if pop else 0
                province_consumption = int(
                    (province_pop // variables.RATIONS_PER) * rationing_multiplier
                )

            if province_consumption < 1:
                province_consumption = 1
            total_needed += province_consumption

        return total_needed if total_needed > 0 else 1


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
                  'distribution_centers', 'gas_stations', 'general_stores',
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


# Returns energy production and consumption from a certain province
def energy_info(province_id):
    from database import get_db_cursor

    with get_db_cursor() as db:
        production = 0
        consumption = 0

        consumers = variables.ENERGY_CONSUMERS
        producers = variables.ENERGY_UNITS

        infra = variables.NEW_INFRA

        # Fetch building quantities from user_buildings for THIS province
        db.execute(
            """
            SELECT bd.name, ub.quantity
            FROM user_buildings ub
            JOIN building_dictionary bd ON bd.building_id = ub.building_id
            WHERE ub.province_id = %s AND bd.name IN %s
            """,
            (province_id, tuple(consumers + producers)),
        )
        rows = db.fetchall()
        result_dict = {row[0]: row[1] for row in rows} if rows else {}
        result = tuple(result_dict.get(name, 0) for name in consumers + producers)

        if not result:
            return 0, 0

        # Calculate consumption from first N fields
        consumption = sum(result[: len(consumers)])

        # Calculate production from remaining fields
        for idx, producer in enumerate(producers):
            producer_count = result[len(consumers) + idx]
            production += producer_count * infra[producer]["plus"]["energy"]

        return consumption, production


# Returns a rations score for a user, from -1 to -1.4
# -1 = Enough or more than enough rations
# -1.4 = No rations at all
def food_stats(user_id):
    from database import get_db_cursor

    with get_db_cursor() as db:
        needed_rations = rations_needed(user_id)

        # Query normalized user_economy table
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
        current_rations = row[0] if row else 0

        # compute distribution capacity if the feature is enabled
        distribution_cap = None
        if variables.FEATURE_RATIONS_DISTRIBUTION:
            # Query normalized user_buildings table — tiered capacity
            db.execute(
                """
                SELECT bd.name, COALESCE(SUM(ub.quantity), 0) AS qty
                FROM user_buildings ub
                JOIN building_dictionary bd ON bd.building_id = ub.building_id
                WHERE ub.user_id = %s
                  AND bd.name IN ('distribution_centers', 'gas_stations',
                                  'general_stores', 'farmers_markets', 'malls')
                GROUP BY bd.name
                """,
                (user_id,),
            )
            distribution_cap = 0
            for brow in db.fetchall():
                bname = brow[0]
                qty = brow[1] or 0
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


def consumer_goods_distribution_capacity(user_id):
    """Return the population that can be served by CG distribution buildings."""
    if not variables.FEATURE_DEMOGRAPHIC_CONSUMPTION:
        return None

    from database import get_db_cursor

    with get_db_cursor() as db:
        # Query normalized user_buildings table — tiered CG capacity
        db.execute(
            """
            SELECT bd.name, COALESCE(SUM(ub.quantity), 0) AS qty
            FROM user_buildings ub
            JOIN building_dictionary bd
                ON bd.building_id = ub.building_id
            WHERE ub.user_id = %s
              AND bd.name IN (
                  'distribution_centers', 'malls',
                  'general_stores', 'gas_stations'
              )
            GROUP BY bd.name
            """,
            (user_id,),
        )
        total = 0
        for row in db.fetchall():
            bname = row[0]
            qty = row[1] or 0
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


# Returns an energy score for a user, from -1 to -1.6
# -1 = Enough or more than enough energy
# -1.6 = No energy at all
def energy_stats(user_id):
    from database import get_db_cursor

    with get_db_cursor() as db:
        # Get all province IDs in one query
        db.execute("SELECT id FROM provinces WHERE userId=%s", (user_id,))
        provinces = db.fetchall()

        total_energy_consumption = 0
        total_energy_production = 0

        for province_id in provinces:
            province_id = province_id[0]

            consumption, production = energy_info(province_id)
            total_energy_consumption += consumption
            total_energy_production += production

    if total_energy_consumption == 0:
        total_energy_consumption = 1

    tcp = (
        total_energy_production / total_energy_consumption
    ) - 1  # Normalizes the score to 0.
    if tcp > 0:
        tcp = 0

    score = -1 + (tcp * variables.NO_ENERGY_TAX_MULTIPLIER)

    return score


# Function for calculating tax income
def calc_ti(user_id):
    from database import get_db_cursor

    with get_db_cursor() as db:
        # Query normalized user_economy table
        db.execute(
            """
            SELECT COALESCE(ue.quantity, 0)
            FROM user_economy ue
            JOIN resource_dictionary rd ON rd.resource_id = ue.resource_id
            WHERE ue.user_id = %s AND rd.name = 'consumer_goods'
            """,
            (user_id,),
        )
        cg_result = db.fetchone()
        consumer_goods = int(cg_result[0] if cg_result else 0)

        # Education policies (may not exist yet)
        try:
            db.execute("SELECT education FROM policies WHERE user_id=%s", (user_id,))
            policies = db.fetchone()[0]
        except Exception:
            policies = []

        # Provinces (may not exist yet)
        try:
            db.execute(
                (
                    "SELECT population, land, pop_children, "
                    "pop_working, pop_elderly FROM provinces "
                    "WHERE userId=%s"
                ),
                (user_id,),
            )
            provinces = db.fetchall()
        except Exception:
            provinces = []

        if not provinces:  # User doesn't have any provinces
            return False, False

        income = 0
        total_cg_need = 0
        has_demographic_data = (
            True
            if (provinces and len(provinces[0]) >= 5 and provinces[0][2] is not None)
            else False
        )

        for province_row in provinces:
            if has_demographic_data:
                population, land, pc, pw, pe = province_row
            else:
                population = province_row[0]
                land = province_row[1]

            land_multiplier = (land - 1) * variables.DEFAULT_LAND_TAX_MULTIPLIER
            if land_multiplier > 1:
                land_multiplier = 1  # Cap 100%

            base_multiplier = variables.DEFAULT_TAX_INCOME

            multiplier = base_multiplier + (base_multiplier * land_multiplier)
            income += multiplier * population

            # Calculate CG need (demographic-based if available)
            if variables.FEATURE_DEMOGRAPHIC_CONSUMPTION and has_demographic_data:
                # Apply healthcare multiplier to elderly CG consumption
                elderly_cg_multiplier = (
                    variables.POLICY_HEALTHCARE_ELDERLY_CG_MULTIPLIER
                    if variables.POLICY_UNIVERSAL_HEALTHCARE in policies
                    else 1.0
                )

                cg_needed = 0
                cg_needed += (
                    pw * variables.DEMO_CONSUMER_GOODS_CONSUMPTION["pop_working"]
                )
                cg_needed += (
                    pc * variables.DEMO_CONSUMER_GOODS_CONSUMPTION["pop_children"]
                )
                cg_needed += (
                    pe
                    * variables.DEMO_CONSUMER_GOODS_CONSUMPTION["pop_elderly"]
                    * elderly_cg_multiplier
                )
                total_cg_need += cg_needed
            else:
                # Fall back to old method: total_population / CONSUMER_GOODS_PER
                total_cg_need += math.ceil(population / variables.CONSUMER_GOODS_PER)

        # Step 1: Calculate distribution capacity bottleneck
        removed_consumer_goods = 0
        if variables.FEATURE_DEMOGRAPHIC_CONSUMPTION:
            dist_capacity = consumer_goods_distribution_capacity(user_id)
            # Step 2: Apply bottleneck logic
            if dist_capacity is not None:
                # Can only consume up to distribution capacity
                available_to_consume = min(consumer_goods, dist_capacity)
            else:
                available_to_consume = consumer_goods

            # Step 3: Apply tax multiplier if enough CG is available
            if total_cg_need != 0:
                if available_to_consume >= total_cg_need:
                    # Full supply available
                    removed_consumer_goods = int(total_cg_need)
                    income *= variables.CONSUMER_GOODS_TAX_MULTIPLIER
                else:
                    # Partial supply: apply reduced multiplier
                    multiplier = available_to_consume / total_cg_need
                    income *= 1 + (0.5 * multiplier)
                    removed_consumer_goods = available_to_consume
            # Note: shortage triggered even if stockpile > distribution cap
        else:
            # Old logic (fallback)
            max_cg = math.ceil(total_cg_need)  # total_cg_need already in unit
            if consumer_goods != 0 and max_cg != 0:
                if max_cg <= consumer_goods:
                    # Enough CG to fully cover consumption
                    removed_consumer_goods = max_cg
                    income *= variables.CONSUMER_GOODS_TAX_MULTIPLIER
                else:
                    # Not enough goods; apply partial multiplier
                    multiplier = consumer_goods / max_cg
                    income *= 1 + (0.5 * multiplier)
                    removed_consumer_goods = consumer_goods

        # Return (income, removed_consumer_goods) where
        # removed_consumer_goods is a positive count
        return math.floor(income), removed_consumer_goods


# (x, y) - (income, removed_consumer_goods)
# * Tested no provinces
# * Tested population=100, land=1, consumer_goods=0 (1, 0)
# * Tested population=100, land=51, consumer_goods=0 (2, 0)
# * Tested population=100000, land=10, consumer_goods=10 (1770, -5)
# * Tested population=100000, land=1, consumer_goods=0 (1000, 0)


# Function for actually giving money to players (OPTIMIZED)
def tax_income():
    from database import get_db_connection
    from psycopg2.extras import execute_batch, RealDictCursor

    try:
        with get_db_connection() as conn:
            if not try_pg_advisory_lock(conn, 9001, "tax_income"):
                return
            db = conn.cursor()
            # Ensure we only run once in a short window
            # (protects against multiple beat schedulers)
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS task_runs (
                    task_name TEXT PRIMARY KEY,
                    last_run TIMESTAMP WITH TIME ZONE
                )
            """
            )
            # Ensure a row exists and lock it to prevent concurrent runs from
            # racing on the last_run check. This uses a fast INSERT ... ON CONFLICT
            # followed by SELECT ... FOR UPDATE so concurrent workers serialize on
            # the task_runs row.
            db.execute(
                "INSERT INTO task_runs (task_name, last_run) VALUES (%s, NULL) "
                "ON CONFLICT DO NOTHING",
                ("tax_income",),
            )

            db.execute(
                "SELECT last_run FROM task_runs WHERE task_name=%s FOR UPDATE",
                ("tax_income",),
            )
            row = db.fetchone()
            if should_skip_task(row, "tax_income"):
                try:
                    release_pg_advisory_lock(conn, 9001)
                except Exception:
                    pass
                return

            db.execute(
                ("UPDATE task_runs SET last_run = now() WHERE task_name = %s"),
                ("tax_income",),
            )
            # Commit last_run immediately so the timestamp persists even if
            # later processing crashes (prevents "stuck" last_run).
            try:
                conn.commit()
            except Exception:
                pass
            start = time.perf_counter()
            dbdict = conn.cursor(cursor_factory=RealDictCursor)

            # Use a cursor table to process users in chunks to avoid large spikes
            db.execute(
                "CREATE TABLE IF NOT EXISTS task_cursors ("
                "task_name TEXT PRIMARY KEY, last_id BIGINT)"
            )
            db.execute(
                "INSERT INTO task_cursors (task_name, last_id) "
                "VALUES (%s, %s) ON CONFLICT DO NOTHING",
                ("tax_income", 0),
            )
            db.execute(
                "SELECT last_id FROM task_cursors WHERE task_name=%s", ("tax_income",)
            )
            last_row = db.fetchone()
            last_id = last_row[0] if last_row and last_row[0] is not None else 0

            # Keep default chunks conservative to reduce lock time per run.
            chunk_size = int(os.getenv("TAX_INCOME_CHUNK_SIZE", "250"))
            db.execute(
                "SELECT id FROM users WHERE id > %s ORDER BY id ASC LIMIT %s",
                (last_id, chunk_size),
            )
            users = db.fetchall()
            all_user_ids = [u[0] for u in users]

            if not all_user_ids:
                # Completed full cycle; reset cursor and immediately
                # re-fetch from the beginning so this run still processes
                # users (avoids wasting every other hourly invocation).
                db.execute(
                    "UPDATE task_cursors SET last_id=0 WHERE task_name=%s",
                    ("tax_income",),
                )
                conn.commit()
                db.execute(
                    "SELECT id FROM users WHERE id > 0 ORDER BY id ASC LIMIT %s",
                    (chunk_size,),
                )
                users = db.fetchall()
                all_user_ids = [u[0] for u in users]
                if not all_user_ids:
                    return  # genuinely no users

            # Bulk load all data upfront to eliminate N+1 queries
            # Load all stats (gold)
            stats_map = {}
            dbdict.execute(
                "SELECT id, gold FROM stats WHERE id = ANY(%s)", (all_user_ids,)
            )
            for row in dbdict.fetchall():
                # Support both RealDictCursor (dict rows)
                # and simple tuple rows returned by test fakes
                if isinstance(row, dict):
                    stats_map[row.get("id") or row.get("Id") or row.get("ID")] = (
                        row.get("gold") or 0
                    )
                else:
                    uid = row[0]
                    gold_val = row[1] if len(row) > 1 else 0
                    stats_map[uid] = gold_val

            # Load all consumer_goods from normalized user_economy
            cg_map = {}
            dbdict.execute(
                """
                SELECT ue.user_id, COALESCE(ue.quantity, 0) AS consumer_goods
                FROM user_economy ue
                JOIN resource_dictionary rd ON rd.resource_id = ue.resource_id
                WHERE ue.user_id = ANY(%s) AND rd.name = 'consumer_goods'
                """,
                (all_user_ids,),
            )
            for row in dbdict.fetchall():
                if isinstance(row, dict):
                    cg_map[
                        row.get("user_id")
                        or row.get("id")
                        or row.get("Id")
                        or row.get("ID")
                    ] = (row.get("consumer_goods") or 0)
                else:
                    uid = row[0]
                    cg_val = row[1] if len(row) > 1 else 0
                    cg_map[uid] = cg_val

            # Load all policies
            policies_map = {}
            dbdict.execute(
                "SELECT user_id, education FROM policies WHERE user_id = ANY(%s)",
                (all_user_ids,),
            )
            for row in dbdict.fetchall():
                if isinstance(row, dict):
                    uid = row.get("user_id") or row.get("userId") or row.get("userid")
                    policies_map[uid] = (
                        row.get("education") if row.get("education") else []
                    )
                else:
                    uid = row[0]
                    education = row[1] if len(row) > 1 and row[1] else []
                    policies_map[uid] = education

            # Load all provinces grouped by user.
            # Include demographic fields so we can compute CG demand
            # without calling calc_ti() per user.
            provinces_map = {}  # user_id -> [(population, land, pc, pw, pe), ...]
            dbdict.execute(
                "SELECT userId, population, land, pop_children, "
                "pop_working, pop_elderly "
                "FROM provinces WHERE userId = ANY(%s)",
                (all_user_ids,),
            )
            for row in dbdict.fetchall():
                if isinstance(row, dict):
                    uid = row.get("userid") or row.get("userId") or row.get("user_id")
                    if uid not in provinces_map:
                        provinces_map[uid] = []
                    provinces_map[uid].append(
                        (
                            row.get("population") or 0,
                            row.get("land") or 0,
                            row.get("pop_children"),
                            row.get("pop_working"),
                            row.get("pop_elderly"),
                        )
                    )
                else:
                    uid = row[0]
                    if len(row) > 5:
                        if uid not in provinces_map:
                            provinces_map[uid] = []
                        provinces_map[uid].append(
                            (row[1], row[2], row[3], row[4], row[5])
                        )
                    else:
                        # Not enough columns returned; treat as no provinces
                        # for this uid
                        if uid not in provinces_map:
                            provinces_map[uid] = []

            # Preload consumer-goods distribution capacity (user-level)
            # to avoid per-user DB queries via consumer_goods_distribution_capacity().
            cg_dist_cap_map = {}
            if variables.FEATURE_DEMOGRAPHIC_CONSUMPTION:
                dbdict.execute(
                    """
                    SELECT ub.user_id, bd.name, COALESCE(SUM(ub.quantity), 0) AS qty
                    FROM user_buildings ub
                    JOIN building_dictionary bd
                        ON bd.building_id = ub.building_id
                    WHERE ub.user_id = ANY(%s)
                      AND bd.name IN (
                          'distribution_centers', 'malls',
                          'general_stores', 'gas_stations'
                      )
                    GROUP BY ub.user_id, bd.name
                    """,
                    (all_user_ids,),
                )
                for row in dbdict.fetchall():
                    if isinstance(row, dict):
                        uid = row.get("user_id")
                        bname = row.get("name")
                        qty = row.get("qty") or 0
                    else:
                        uid = row[0]
                        bname = row[1]
                        qty = row[2] if len(row) > 2 else 0
                    cap = variables.CONSUMER_GOODS_DISTRIBUTION_PER_BUILDING.get(
                        bname,
                        variables.CONSUMER_GOODS_DISTRIBUTION_PER_BUILDING_DEFAULT,
                    )
                    cg_dist_cap_map[uid] = cg_dist_cap_map.get(uid, 0) + qty * cap

            # Prepare batch updates
            money_updates = []
            cg_updates = []

            for user_id in all_user_ids:
                current_money = stats_map.get(user_id)
                if current_money is None:
                    continue

                provinces = provinces_map.get(user_id) or []
                if not provinces:
                    continue

                consumer_goods = int(cg_map.get(user_id, 0) or 0)
                policies = policies_map.get(user_id, []) or []

                income = 0.0
                total_cg_need = 0.0
                has_demographic_data = all(
                    len(p) >= 5
                    and p[2] is not None
                    and p[3] is not None
                    and p[4] is not None
                    for p in provinces
                )

                for population, land, pc, pw, pe in provinces:
                    land_multiplier = (land - 1) * variables.DEFAULT_LAND_TAX_MULTIPLIER
                    if land_multiplier > 1:
                        land_multiplier = 1

                    base_multiplier = variables.DEFAULT_TAX_INCOME
                    multiplier = base_multiplier + (base_multiplier * land_multiplier)
                    income += multiplier * population

                    if (
                        variables.FEATURE_DEMOGRAPHIC_CONSUMPTION
                        and has_demographic_data
                    ):
                        elderly_cg_multiplier = (
                            variables.POLICY_HEALTHCARE_ELDERLY_CG_MULTIPLIER
                            if variables.POLICY_UNIVERSAL_HEALTHCARE in policies
                            else 1.0
                        )
                        cg_needed = 0
                        cg_needed += (
                            pw or 0
                        ) * variables.DEMO_CONSUMER_GOODS_CONSUMPTION["pop_working"]
                        cg_needed += (
                            pc or 0
                        ) * variables.DEMO_CONSUMER_GOODS_CONSUMPTION["pop_children"]
                        cg_needed += (
                            (pe or 0)
                            * variables.DEMO_CONSUMER_GOODS_CONSUMPTION["pop_elderly"]
                            * elderly_cg_multiplier
                        )
                        total_cg_need += cg_needed
                    else:
                        total_cg_need += math.ceil(
                            population / variables.CONSUMER_GOODS_PER
                        )

                removed_consumer_goods = 0
                if variables.FEATURE_DEMOGRAPHIC_CONSUMPTION:
                    dist_capacity = cg_dist_cap_map.get(user_id, 0)
                    available_to_consume = min(consumer_goods, dist_capacity)
                    if total_cg_need != 0:
                        if available_to_consume >= total_cg_need:
                            removed_consumer_goods = int(total_cg_need)
                            income *= variables.CONSUMER_GOODS_TAX_MULTIPLIER
                        else:
                            cg_multiplier = available_to_consume / total_cg_need
                            income *= 1 + (0.5 * cg_multiplier)
                            removed_consumer_goods = int(available_to_consume)
                else:
                    max_cg = math.ceil(total_cg_need)
                    if consumer_goods != 0 and max_cg != 0:
                        if max_cg <= consumer_goods:
                            removed_consumer_goods = max_cg
                            income *= variables.CONSUMER_GOODS_TAX_MULTIPLIER
                        else:
                            cg_multiplier = consumer_goods / max_cg
                            income *= 1 + (0.5 * cg_multiplier)
                            removed_consumer_goods = int(consumer_goods)

                money = int(math.floor(income))

                if not money:
                    continue

                msg = (
                    f"Updated money for user id: {user_id}."
                    f" {current_money} -> {current_money + money} (+{money})"
                )
                print(msg)

                money_updates.append((money, user_id))
                if removed_consumer_goods and removed_consumer_goods != 0:
                    cg_updates.append((abs(removed_consumer_goods), user_id))
            # Execute batch updates
            if money_updates:
                execute_batch(
                    db,
                    "UPDATE stats SET gold=gold+%s WHERE id=%s",
                    money_updates,
                    page_size=100,
                )
            if cg_updates:
                try:
                    # Get consumer_goods resource_id
                    db.execute(
                        "SELECT resource_id FROM resource_dictionary "
                        "WHERE name='consumer_goods'"
                    )
                    cg_resource_id = db.fetchone()[0]

                    # Batch update user_economy
                    cg_sql = (
                        "UPDATE user_economy SET quantity=GREATEST("
                        "quantity-%s, 0) WHERE user_id=%s AND resource_id=%s"
                    )
                    cg_updates_with_resource = [
                        (qty, uid, cg_resource_id) for qty, uid in cg_updates
                    ]
                    execute_batch(db, cg_sql, cg_updates_with_resource, page_size=100)
                except AttributeError:
                    # DB cursor in tests may not support psycopg2 extras
                    # fall back to individual updates
                    db.execute(
                        "SELECT resource_id FROM resource_dictionary "
                        "WHERE name='consumer_goods'"
                    )
                    cg_resource_id = db.fetchone()[0]
                    for qty, uid in cg_updates:
                        db.execute(
                            "UPDATE user_economy SET quantity=GREATEST("
                            "quantity-%s, 0) WHERE user_id=%s AND resource_id=%s",
                            (qty, uid, cg_resource_id),
                        )

                # Invalidate cache for affected users (best-effort)
                try:
                    from database import invalidate_user_cache

                    for _, uid in cg_updates:
                        try:
                            invalidate_user_cache(uid)
                        except Exception:
                            pass
                except Exception:
                    pass

            try:
                try:
                    conn.commit()
                except AttributeError:
                    # Fake connection used in tests may not implement commit
                    pass
            except Exception as e:
                try:
                    conn.rollback()
                except Exception:
                    pass
                handle_exception(e)

            # Best-effort: invalidate user cache for all processed users so any
            # caller reading resources/revenue doesn't hit stale values in cache.
            try:
                from database import invalidate_user_cache

                for uid in all_user_ids:
                    try:
                        invalidate_user_cache(uid)
                    except Exception:
                        pass
            except Exception:
                pass

            # Update the progress cursor to the last processed user so subsequent
            # task runs resume from the next ID and avoid reprocessing the same set
            try:
                if all_user_ids:
                    last_processed = max(all_user_ids)
                    db.execute(
                        "UPDATE task_cursors SET last_id=%s WHERE task_name=%s",
                        (last_processed, "tax_income"),
                    )
                    try:
                        conn.commit()
                    except Exception:
                        pass
            except Exception as e:
                print(f"Failed to update task cursor for tax_income: {e}")

            duration = time.perf_counter() - start
            print(
                f"tax_income: updated {len(money_updates)} users in {duration:.2f}s "
                f"(cg updates: {len(cg_updates)})"
            )

            # Emit a metric (best-effort)
            try:
                from helpers import record_task_metric

                record_task_metric("tax_income", duration)
            except Exception:
                pass
    except psycopg2.InterfaceError as e:
        print(
            f"Database connection error in tax_income: {e}. Skipping tax income update."
        )
        return
    finally:
        try:
            release_pg_advisory_lock(conn, 9001)
        except Exception:
            pass


# Function for calculating population growth for a given province
def calc_pg(pId, rations):
    from database import get_db_cursor

    with get_db_cursor() as db:
        # Single query to get all province data at once
        db.execute(
            """SELECT p.population, p.cityCount, p.land, p.happiness,
                      p.pollution, p.userId, pol.education
               FROM provinces p
               LEFT JOIN policies pol ON pol.user_id = p.userId
               WHERE p.id=%s""",
            (pId,),
        )
        row = db.fetchone()
        if not row:
            return rations, 0

        curPop = row[0] if row[0] is not None else 0
        cities = row[1] if row[1] is not None else 0
        land = row[2] if row[2] is not None else 0
        happiness = int(row[3]) if row[3] is not None else 0
        pollution = row[4] if row[4] is not None else 0
        # row[6] (policies) no longer used after policy overhaul

        maxPop = variables.DEFAULT_MAX_POPULATION  # Base max population: 1 million
        maxPop += (
            cities * variables.CITY_MAX_POPULATION_ADDITION
        )  # Each city adds 750,000
        maxPop += (
            land * variables.LAND_MAX_POPULATION_ADDITION
        )  # Each land slot adds 120,000

        # Calculate happiness impact on max population
        happiness_multiplier = (
            (happiness - 50) * variables.DEFAULT_HAPPINESS_GROWTH_MULTIPLIER / 50
        )

        # Calculate pollution impact on max population
        pollution_multiplier = (
            (pollution - 50) * -variables.DEFAULT_POLLUTION_GROWTH_MULTIPLIER / 50
        )

        maxPop = int(maxPop * (1 + happiness_multiplier + pollution_multiplier))

        if maxPop < variables.DEFAULT_MAX_POPULATION:
            maxPop = variables.DEFAULT_MAX_POPULATION

        rations_needed = curPop // variables.RATIONS_PER

        if rations_needed < 1:
            rations_needed = 1  # Trying to not get division by zero error

        rations_needed_percent = rations / rations_needed
        if rations_needed_percent > 1:
            rations_needed_percent = 1

        # Slower, controlled population growth (prevents snowballing)
        base_growth_rate = rations_needed_percent * 0.15

        # Diminishing returns: growth slows as population approaches max
        pop_ratio = curPop / maxPop if maxPop > 0 else 1
        diminishing_factor = max(0.05, 1 - (pop_ratio**2))
        growth_rate = base_growth_rate * diminishing_factor

        # Calculates the new rations of the player
        new_rations = rations - rations_needed
        if new_rations < 0:
            new_rations = 0
        new_rations = int(new_rations)

        newPop = int(round((maxPop / 100) * growth_rate))

        fullPop = int(curPop + newPop)

        if fullPop < 0:
            fullPop = 0

        return new_rations, fullPop


# Optimized population growth to minimize per-province queries and log noise
def population_growth():  # Function for growing population
    from database import get_db_connection
    from psycopg2.extras import execute_batch, RealDictCursor

    with get_db_connection() as conn:
        # Acquire advisory lock to prevent concurrent runs
        if not try_pg_advisory_lock(conn, 9003, "population_growth"):
            return

        db = conn.cursor()

        # Ensure single run within a short window to prevent duplicate hourly updates
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS task_runs (
                task_name TEXT PRIMARY KEY,
                last_run TIMESTAMP WITH TIME ZONE
            )
        """
        )
        db.execute(
            "INSERT INTO task_runs (task_name, last_run) VALUES (%s, NULL) "
            "ON CONFLICT DO NOTHING",
            ("population_growth",),
        )
        db.execute(
            "SELECT last_run FROM task_runs WHERE task_name=%s FOR UPDATE",
            ("population_growth",),
        )
        row = db.fetchone()
        if should_skip_task(row, "population_growth"):
            try:
                release_pg_advisory_lock(conn, 9003)
            except Exception:
                pass
            return

        db.execute(
            "UPDATE task_runs SET last_run = now() WHERE task_name = %s",
            ("population_growth",),
        )
        # Commit last_run immediately so the timestamp persists even if
        # later processing crashes (prevents "stuck" last_run).
        try:
            conn.commit()
        except Exception:
            pass

        dbdict = conn.cursor(cursor_factory=RealDictCursor)

        CHUNK_SIZE = 200

        # Preload province IDs only (lightweight) to chunk the work
        dbdict.execute(
            """
             SELECT p.id, p.userId, p.population, p.cityCount, p.land,
                 p.happiness, p.pollution, p.productivity,
                 COALESCE(p.pop_children, 0) AS pop_children,
                 COALESCE(p.pop_working, 0) AS pop_working,
                 COALESCE(p.pop_elderly, 0) AS pop_elderly
             FROM provinces p
             JOIN users u ON u.id = p.userId
            ORDER BY userId ASC
            """
        )
        all_provinces = dbdict.fetchall()

        if not all_provinces:
            try:
                release_pg_advisory_lock(conn, 9003)
            except Exception:
                pass
            return

        all_user_ids = sorted(set(row["userid"] for row in all_provinces))

        # Get rations resource_id (constant, one query)
        db.execute("SELECT resource_id FROM resource_dictionary WHERE name='rations'")
        rations_resource_id = db.fetchone()[0]

        # Ensure user_economy rows exist for rations (batch, all users)
        execute_batch(
            db,
            """
            INSERT INTO user_economy (user_id, resource_id, quantity)
            VALUES (%s, %s, 0)
            ON CONFLICT (user_id, resource_id) DO NOTHING
            """,
            [(uid, rations_resource_id) for uid in all_user_ids],
        )

        # Preload rations for all users (one query)
        dbdict.execute(
            """
            SELECT ue.user_id, COALESCE(ue.quantity, 0) AS rations
            FROM user_economy ue
            WHERE ue.user_id = ANY(%s) AND ue.resource_id = %s
            """,
            (all_user_ids, rations_resource_id),
        )
        ration_map = {row["user_id"]: row["rations"] for row in dbdict.fetchall()}

        # Preload distribution capacity per user
        dist_cap_map = {}
        if variables.FEATURE_RATIONS_DISTRIBUTION:
            dbdict.execute(
                """
                SELECT ub.user_id, bd.name, COALESCE(SUM(ub.quantity), 0) AS qty
                FROM user_buildings ub
                JOIN building_dictionary bd
                    ON bd.building_id = ub.building_id
                WHERE ub.user_id = ANY(%s)
                  AND bd.name IN (
                      'distribution_centers', 'gas_stations',
                      'general_stores', 'farmers_markets', 'malls'
                  )
                GROUP BY ub.user_id, bd.name
                """,
                (all_user_ids,),
            )
            for row in dbdict.fetchall():
                uid = row["user_id"]
                bname = row["name"]
                qty = row["qty"] or 0
                cap = variables.RATIONS_DISTRIBUTION_PER_BUILDING.get(
                    bname, variables.RATIONS_DISTRIBUTION_PER_BUILDING_DEFAULT
                )
                dist_cap_map[uid] = dist_cap_map.get(uid, 0) + qty * cap

        conn.commit()  # Release read locks from preload queries

        # PHASE 1: Calculate total rations needed per user (sum across all provinces)
        user_total_rations_needed = {}
        for province_row in all_provinces:
            user_id = province_row["userid"]
            curPop = province_row["population"] or 0
            rations_needed = curPop // variables.RATIONS_PER
            if rations_needed < 1:
                rations_needed = 1
            user_total_rations_needed[user_id] = (
                user_total_rations_needed.get(user_id, 0) + rations_needed
            )

        # PHASE 2: Apply distribution-center bottleneck.
        user_rations_to_deduct = {}
        user_effective_rations = {}
        for uid, needed in user_total_rations_needed.items():
            warehouse = ration_map.get(uid, 0) or 0
            if variables.FEATURE_RATIONS_DISTRIBUTION:
                dist_cap = dist_cap_map.get(uid, 0)
                distributable = min(warehouse, dist_cap)
            else:
                distributable = warehouse
            actually_consumed = min(needed, distributable)
            user_rations_to_deduct[uid] = actually_consumed
            user_effective_rations[uid] = distributable

        def calc_population_growth(province_row):
            """Calculate population growth for a single province."""
            user_id = province_row["userid"]
            curPop = province_row["population"] or 0
            cities = province_row["citycount"] or 0
            land = province_row["land"] or 0
            happiness = int(province_row.get("happiness") or 0)
            pollution = province_row.get("pollution") or 0

            maxPop = variables.DEFAULT_MAX_POPULATION
            maxPop += cities * variables.CITY_MAX_POPULATION_ADDITION
            maxPop += land * variables.LAND_MAX_POPULATION_ADDITION

            happiness_multiplier = (
                (happiness - 50) * variables.DEFAULT_HAPPINESS_GROWTH_MULTIPLIER / 50
            )
            pollution_multiplier = (
                (pollution - 50) * -variables.DEFAULT_POLLUTION_GROWTH_MULTIPLIER / 50
            )

            maxPop = int(maxPop * (1 + happiness_multiplier + pollution_multiplier))
            if maxPop < variables.DEFAULT_MAX_POPULATION:
                maxPop = variables.DEFAULT_MAX_POPULATION

            total_needed = user_total_rations_needed.get(user_id, 1)
            effective_rations = user_effective_rations.get(user_id, 0) or 0
            rations_ratio = effective_rations / total_needed if total_needed > 0 else 0
            if rations_ratio > 1:
                rations_ratio = 1

            base_growth_rate = rations_ratio * 0.15

            pop_ratio = curPop / maxPop if maxPop > 0 else 1
            diminishing_factor = max(0.05, 1 - (pop_ratio**2))
            growth_rate = base_growth_rate * diminishing_factor

            newPop = int(round((maxPop / 100) * growth_rate))

            fullPop = int(curPop + newPop)
            if fullPop < 0:
                fullPop = 0

            return fullPop

        # PHASE 3 + 4: Process and write in chunks to avoid holding
        # the DB connection for the entire province set.
        total_pop_updates = 0
        total_rations_deducted = 0
        rations_deducted_users = set()

        for chunk_start in range(0, len(all_provinces), CHUNK_SIZE):
            chunk = all_provinces[chunk_start : chunk_start + CHUNK_SIZE]

            population_updates = []
            for province_row in chunk:
                try:
                    old_population = province_row["population"] or 0
                    new_population = calc_population_growth(province_row)
                    population_growth_amount = new_population - old_population

                    # Sync demographics to match new population total.
                    # This handles: growth (add to children), decline
                    # (proportional reduction), and accumulated drift.
                    # The DB trigger also enforces this, but computing
                    # correctly here avoids relying on proportional
                    # redistribution in the trigger.
                    pop_c = province_row["pop_children"]
                    pop_w = province_row["pop_working"]
                    pop_e = province_row["pop_elderly"]
                    demo_sum = pop_c + pop_w + pop_e

                    if new_population <= 0:
                        new_c, new_w, new_e = 0, 0, 0
                    elif demo_sum == 0:
                        # No demographics yet — seed as all children
                        new_c = new_population
                        new_w, new_e = 0, 0
                    elif population_growth_amount > 0 and demo_sum <= new_population:
                        # Growth: add delta to children (existing behavior)
                        new_c = pop_c + (new_population - demo_sum)
                        new_w, new_e = pop_w, pop_e
                    else:
                        # Decline or drift: scale proportionally
                        ratio = new_population / demo_sum
                        new_c = int(round(pop_c * ratio))
                        new_e = int(round(pop_e * ratio))
                        # Give remainder to working to avoid rounding mismatches
                        new_w = new_population - new_c - new_e

                    # Single atomic UPDATE for population + demographics
                    population_updates.append(
                        (
                            new_population,
                            max(0, new_c),
                            max(0, new_w),
                            max(0, new_e),
                            province_row["id"],
                        )
                    )
                except Exception as e:
                    handle_exception(e)
                    continue

            # Collect rations deductions for users in this chunk
            chunk_user_ids = set(row["userid"] for row in chunk)
            # Only deduct rations once per user (on the chunk that first sees them)
            new_ration_users = chunk_user_ids - rations_deducted_users
            rations_updates = [
                (user_rations_to_deduct[uid], uid, rations_resource_id)
                for uid in new_ration_users
                if uid in user_rations_to_deduct
            ]
            rations_deducted_users.update(new_ration_users)

            # Write this chunk's updates
            if rations_updates:
                execute_batch(
                    db,
                    """
                    UPDATE user_economy
                    SET quantity = GREATEST(0, quantity - %s)
                    WHERE user_id=%s AND resource_id=%s
                    """,
                    rations_updates,
                )
                total_rations_deducted += len(rations_updates)

            if population_updates:
                execute_batch(
                    db,
                    """UPDATE provinces
                       SET population = %s,
                           pop_children = %s,
                           pop_working = %s,
                           pop_elderly = %s
                       WHERE id = %s""",
                    population_updates,
                )
                total_pop_updates += len(population_updates)

            # Commit after each chunk to release locks
            try:
                conn.commit()
            except Exception:
                pass

        print(
            f"population_growth: updated {total_pop_updates} provinces "
            f"across {len(all_user_ids)} users, "
            f"consumed rations from {total_rations_deducted} users"
        )

        try:
            release_pg_advisory_lock(conn, 9003)
        except Exception:
            pass


def find_unit_category(unit):
    categories = variables.INFRA_TYPE_BUILDINGS
    for name, list in categories.items():
        if unit in list:
            return name
    return False


"""
Tested features:
- resource giving
- unit with enough resources selection
- energy didnt change
- removal of resources
- good monetary removal
"""


# PHASE 3: Workforce & Aging System Functions
# ============================================


def apply_population_aging(province_id):
    """
    Apply daily aging and education graduation to a province.

    Process:
    1. Elderly death: pop_elderly *= (1 - DEMO_AGING_RATES['elderly_death'])
    2. Working -> Elderly: pop_elderly +=
       pop_working * DEMO_AGING_RATES['working_to_elderly']
    3. Children -> Working: shift based on education graduation

    Education graduation:
    - Assumes each school/university has capacity
      (defined in BUILDING_EMPLOYMENT_MATRICES)
    - Graduates are placed into edu_highschool or edu_college
      based on graduation_priority
    - Non-graduate educated children stay as edu_none

    Returns: True if successful, False if province
    not found or error
    """
    if not variables.FEATURE_PHASE3_WORKFORCE:
        return False

    from database import get_db_cursor

    try:
        with get_db_cursor() as db:
            # Fetch current demographic state
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
                return False

            pop_children, pop_working, pop_elderly, user_id = row

            # Check policies for Universal Healthcare
            db.execute(
                "SELECT education FROM policies WHERE user_id = %s",
                (user_id,),
            )
            policy_row = db.fetchone()
            policies = policy_row[0] if policy_row else []

            # Apply healthcare reduction to elderly death rate
            elderly_death_rate = variables.DEMO_AGING_RATES["elderly_death"]
            if variables.POLICY_UNIVERSAL_HEALTHCARE in policies:
                elderly_death_rate *= (
                    variables.POLICY_HEALTHCARE_ELDERLY_DEATH_REDUCTION
                )

            # Step 1: Apply elderly death rate
            elderly_deaths = int(round(pop_elderly * elderly_death_rate))
            pop_elderly = max(0, pop_elderly - elderly_deaths)

            # Step 2: Shift working -> elderly
            working_to_elderly = int(
                round(pop_working * variables.DEMO_AGING_RATES["working_to_elderly"])
            )
            pop_elderly += working_to_elderly
            pop_working = max(0, pop_working - working_to_elderly)

            # Step 3: Shift children -> working (with education graduation logic)
            # Calculate total graduation capacity from schools/universities
            # in THIS province
            db.execute(
                """
                SELECT COALESCE(SUM(ub.quantity), 0)
                FROM user_buildings ub
                JOIN building_dictionary bd
                    ON bd.building_id = ub.building_id
                WHERE ub.province_id = %s
                    AND bd.name IN ('high_school', 'university')
                """,
                (province_id,),
            )
            school_capacity_result = db.fetchone()
            school_capacity = (
                int(school_capacity_result[0] * 100) if school_capacity_result else 0
            )  # 100 students per building

            # Apply Mandatory Schooling policy to graduation rate
            graduation_rate = variables.DEMO_AGING_RATES["children_to_working"]
            if variables.POLICY_MANDATORY_SCHOOLING in policies:
                graduation_rate *= variables.POLICY_SCHOOLING_GRADUATION_MULTIPLIER

            # Calculate how many children can graduate
            can_graduate = min(
                pop_children,
                int(round(pop_children * graduation_rate)),
            )
            graduates = (
                min(can_graduate, school_capacity // 100) if school_capacity > 0 else 0
            )

            # Remaining children who age but don't graduate
            non_graduates = can_graduate - graduates

            # Update education columns based on graduation
            if graduates > 0:
                grad_priority = variables.EDUCATION_GRADUATION_PRIORITY
                # Distribute graduates based on priority
                # (first option gets all unless capacity runs out)
                for edu_level in grad_priority:
                    if edu_level == "university":
                        db.execute(
                            "UPDATE provinces SET edu_college = "
                            "edu_college + %s WHERE id = %s",
                            (graduates, province_id),
                        )
                    elif edu_level == "high_school":
                        db.execute(
                            "UPDATE provinces SET edu_highschool = "
                            "edu_highschool + %s WHERE id = %s",
                            (graduates, province_id),
                        )
                    break  # Only place in primary priority for now

            if non_graduates > 0:
                db.execute(
                    "UPDATE provinces SET edu_none = edu_none + %s " "WHERE id = %s",
                    (non_graduates, province_id),
                )

            # Children who do age (educated or not)
            pop_working += can_graduate
            pop_children = max(0, pop_children - can_graduate)

            # Write back updated demographics
            db.execute(
                """
                UPDATE provinces
                SET pop_children = %s,
                    pop_working = %s,
                    pop_elderly = %s
                WHERE id = %s
                """,
                (pop_children, pop_working, pop_elderly, province_id),
            )

            return True
    except Exception as e:
        log_verbose(f"apply_population_aging error on province {province_id}: {e}")
        return False


def calculate_workforce_available(user_id):
    """
    Calculate the total workforce available for employment by education bracket.

    Returns:
        {
            'edu_none': count,
            'edu_highschool': count,
            'edu_college': count,
            'total': count
        }
    """
    if not variables.FEATURE_PHASE3_WORKFORCE:
        return {"edu_none": 0, "edu_highschool": 0, "edu_college": 0, "total": 0}

    from database import get_db_cursor

    try:
        with get_db_cursor() as db:
            db.execute(
                """
                SELECT COALESCE(SUM(edu_none), 0) as edu_none,
                       COALESCE(SUM(edu_highschool), 0) as edu_highschool,
                       COALESCE(SUM(edu_college), 0) as edu_college
                FROM provinces
                WHERE userId = %s
                """,
                (user_id,),
            )
            row = db.fetchone()
            if not row:
                return {
                    "edu_none": 0,
                    "edu_highschool": 0,
                    "edu_college": 0,
                    "total": 0,
                }

            edu_none, edu_highschool, edu_college = row[0], row[1], row[2]
            total = edu_none + edu_highschool + edu_college

            return {
                "edu_none": int(edu_none),
                "edu_highschool": int(edu_highschool),
                "edu_college": int(edu_college),
                "total": int(total),
            }
    except Exception as e:
        log_verbose(f"calculate_workforce_available error for user {user_id}: {e}")
        return {"edu_none": 0, "edu_highschool": 0, "edu_college": 0, "total": 0}


def apply_workforce_hiring_and_debuffs(user_id):
    """
    Calculate workforce hiring, efficiency multiplier, and apply debuffs.

    Process:
    1. Tally job openings from all user's buildings using BUILDING_EMPLOYMENT_MATRICES
    2. Match available workers to jobs (prioritizing education requirements)
    3. Calculate unemployment rate: (pop_working - slots_filled) / pop_working
    4. Apply UNEMPLOYMENT_HAPPINESS_PENALTY if unemployment > UNEMPLOYMENT_THRESHOLD
    5. Calculate pension ratio: pop_elderly / pop_working
    6. Apply PENSION_CRISIS_GOLD_PENALTY if ratio > PENSION_CRISIS_RATIO
    7. Return efficiency multiplier for building production

    Returns:
        {
            'jobs_needed': int,
            'jobs_available': int,
            'unemployment_rate': float (0.0-1.0),
            'pension_ratio': float (0.0+),
            'efficiency_multiplier': float (0.2-1.0 clamped),
            'happiness_penalty': int,
            'gold_penalty': int
        }
    """
    if not variables.FEATURE_PHASE3_WORKFORCE:
        return {
            "jobs_needed": 0,
            "jobs_available": 0,
            "unemployment_rate": 0.0,
            "pension_ratio": 0.0,
            "efficiency_multiplier": 1.0,
            "happiness_penalty": 0,
            "gold_penalty": 0,
        }

    from database import get_db_cursor

    try:
        with get_db_cursor() as db:
            # Get workforce available
            workforce = calculate_workforce_available(user_id)
            total_working = workforce["total"]

            # Get population demographics
            db.execute(
                """
                SELECT COALESCE(SUM(pop_working), 0) as total_working,
                       COALESCE(SUM(pop_elderly), 0) as total_elderly
                FROM provinces
                WHERE userId = %s
                """,
                (user_id,),
            )
            demo_row = db.fetchone()
            if not demo_row:
                return {
                    "jobs_needed": 0,
                    "jobs_available": 0,
                    "unemployment_rate": 0.0,
                    "pension_ratio": 0.0,
                    "efficiency_multiplier": 1.0,
                    "happiness_penalty": 0,
                    "gold_penalty": 0,
                }

            total_pop_working = int(demo_row[0])
            total_pop_elderly = int(demo_row[1])

            # Calculate total job openings from buildings
            building_matrices = variables.BUILDING_EMPLOYMENT_MATRICES

            # Get all buildings for user
            db.execute(
                """
                SELECT bd.name, COALESCE(ub.quantity, 0) as count
                FROM user_buildings ub
                JOIN building_dictionary bd ON bd.building_id = ub.building_id
                WHERE ub.user_id = %s
                """,
                (user_id,),
            )
            building_counts = {row[0]: int(row[1]) for row in db.fetchall()}

            # Calculate total jobs needed
            jobs_needed = 0
            for building_name, matrix_data in building_matrices.items():
                workers_per = matrix_data.get("worker_count", 0)
                building_count = building_counts.get(building_name, 0)
                jobs_needed += workers_per * building_count

            # For now: jobs available = workers available (simplified hiring)
            # Future: could implement education requirement matching
            jobs_available = total_working

            # Calculate unemployment rate
            unemployment_rate = 0.0
            if total_pop_working > 0:
                unemployment_rate = max(0.0, 1.0 - (jobs_available / total_pop_working))

            # Calculate pension ratio
            pension_ratio = 0.0
            if total_pop_working > 0:
                pension_ratio = total_pop_elderly / total_pop_working

            # Calculate efficiency multiplier (Chernobyl rule)
            # If jobs_available < jobs_needed: production efficiency reduced
            if jobs_needed > 0:
                employment_ratio = jobs_available / jobs_needed
                # Min efficiency 20% (PRODUCTION_EFFICIENCY_MIN)
                efficiency_multiplier = max(
                    variables.PRODUCTION_EFFICIENCY_MIN, employment_ratio
                )
            else:
                efficiency_multiplier = 1.0

            # Apply debuffs
            happiness_penalty = 0
            gold_penalty = 0

            if unemployment_rate > variables.UNEMPLOYMENT_THRESHOLD:
                happiness_penalty = variables.UNEMPLOYMENT_HAPPINESS_PENALTY

            if pension_ratio > variables.PENSION_CRISIS_RATIO:
                gold_penalty = variables.PENSION_CRISIS_GOLD_PENALTY

            return {
                "jobs_needed": int(jobs_needed),
                "jobs_available": int(jobs_available),
                "unemployment_rate": float(unemployment_rate),
                "pension_ratio": float(pension_ratio),
                "efficiency_multiplier": float(efficiency_multiplier),
                "happiness_penalty": int(happiness_penalty),
                "gold_penalty": int(gold_penalty),
            }
    except Exception as e:
        log_verbose(f"apply_workforce_hiring_and_debuffs error for user {user_id}: {e}")
        return {
            "jobs_needed": 0,
            "jobs_available": 0,
            "unemployment_rate": 0.0,
            "pension_ratio": 0.0,
            "efficiency_multiplier": 1.0,
            "happiness_penalty": 0,
            "gold_penalty": 0,
        }


def generate_province_revenue():  # Runs each hour
    from database import get_db_connection
    from psycopg2.extras import RealDictCursor, execute_batch

    start_time = time.perf_counter()
    processed = 0
    skipped_for_lock = False

    with get_db_connection() as conn:
        if not try_pg_advisory_lock(conn, 9002, "generate_province_revenue"):
            skipped_for_lock = True
            return
        db = conn.cursor()
        # Ensure single run within a short window to prevent duplicate hourly updates
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS task_runs (
                task_name TEXT PRIMARY KEY,
                last_run TIMESTAMP WITH TIME ZONE
            )
        """
        )
        db.execute(
            "INSERT INTO task_runs (task_name, last_run) VALUES (%s, NULL) "
            "ON CONFLICT DO NOTHING",
            ("generate_province_revenue",),
        )
        db.execute(
            "SELECT last_run FROM task_runs WHERE task_name=%s FOR UPDATE",
            ("generate_province_revenue",),
        )
        row = db.fetchone()
        if should_skip_task(row, "generate_province_revenue"):
            try:
                release_pg_advisory_lock(conn, 9002)
            except Exception:
                pass
            return

        db.execute(
            "UPDATE task_runs SET last_run = now() WHERE task_name = %s",
            ("generate_province_revenue",),
        )
        # Commit the last_run update immediately so it persists even if
        # later processing crashes.  This prevents the task from appearing
        # "stuck" at a stale last_run date after transient failures.
        try:
            conn.commit()
        except Exception:
            pass
        dbdict = conn.cursor(cursor_factory=RealDictCursor)

        columns = variables.BUILDINGS

        province_resources = [
            "energy",
            "population",
            "happiness",
            "pollution",
            "productivity",
            "consumer_spending",
        ]
        percentage_based = [
            "happiness",
            "productivity",
            "consumer_spending",
            "pollution",
        ]

        energy_consumers = variables.ENERGY_CONSUMERS
        user_resources = variables.RESOURCES
        infra = variables.NEW_INFRA

        try:
            # Chunked select to process a limited number of provinces per run
            db.execute(
                "CREATE TABLE IF NOT EXISTS task_cursors ("
                "task_name TEXT PRIMARY KEY, last_id BIGINT)"
            )
            db.execute(
                "INSERT INTO task_cursors (task_name, last_id) "
                "VALUES (%s, %s) ON CONFLICT DO NOTHING",
                ("generate_province_revenue", 0),
            )
            db.execute(
                "SELECT last_id FROM task_cursors WHERE task_name=%s",
                ("generate_province_revenue",),
            )
            last_row = db.fetchone()
            last_proc = last_row[0] if last_row and last_row[0] is not None else 0
            # Smaller chunks lower transaction time and reduce player-facing lock waits.
            chunk = int(os.getenv("PROVINCE_REVENUE_CHUNK_SIZE", "200"))
            db.execute(
                "SELECT p.id, p.userId, p.land, p.productivity "
                "FROM provinces p "
                "WHERE p.id > %s ORDER BY p.id ASC LIMIT %s",
                (last_proc, chunk),
            )
            infra_ids = db.fetchall()
            # If this chunk has no rows, reset cursor and immediately
            # re-fetch from the beginning so this run still processes
            # provinces (avoids wasting every other hourly invocation).
            if not infra_ids:
                try:
                    db.execute(
                        "UPDATE task_cursors SET last_id=0 WHERE task_name=%s",
                        ("generate_province_revenue",),
                    )
                    try:
                        conn.commit()
                    except Exception:
                        pass
                    db.execute(
                        "SELECT p.id, p.userId, p.land, p.productivity "
                        "FROM provinces p "
                        "WHERE p.id > 0 ORDER BY p.id ASC LIMIT %s",
                        (chunk,),
                    )
                    infra_ids = db.fetchall()
                except Exception:
                    pass
                if not infra_ids:
                    return  # genuinely no provinces
        except Exception:
            infra_ids = []

        # ============ BULK PRELOAD DATA TO ELIMINATE N+1 QUERIES ============
        # Get all unique user_ids and province_ids
        all_user_ids = list(set(row[1] for row in infra_ids))
        all_province_ids = [row[0] for row in infra_ids]

        # Preload all upgrades for all users at once (instead of per-user calls)
        legacy_upgrade_to_tech = {
            "betterengineering": "better_engineering",
            "cheapermaterials": "cheaper_materials",
            "onlineshopping": "online_shopping",
            "governmentregulation": "government_regulation",
            "nationalhealthinstitution": "national_health_institution",
            "highspeedrail": "high_speed_rail",
            "advancedmachinery": "advanced_machinery",
            "strongerexplosives": "stronger_explosives",
            "widespreadpropaganda": "widespread_propaganda",
            "increasedfunding": "increased_funding",
            "automationintegration": "automation_integration",
            "largerforges": "larger_forges",
            "lootingteams": "looting_teams",
            "organizedsupplylines": "organized_supply_lines",
            "largestorehouses": "large_storehouses",
            "ballisticmissilesilo": "ballistic_missile_silo",
            "icbmsilo": "icbm_silo",
            "nucleartestingfacility": "nuclear_testing_facility",
        }
        tech_to_legacy = {v: k for k, v in legacy_upgrade_to_tech.items()}

        upgrades_map = {
            uid: {k: False for k in legacy_upgrade_to_tech.keys()}
            for uid in all_user_ids
        }
        if all_user_ids:
            dbdict.execute(
                """
                SELECT ut.user_id, td.name
                FROM user_tech ut
                JOIN tech_dictionary td ON td.tech_id = ut.tech_id
                WHERE ut.user_id = ANY(%s) AND ut.is_unlocked = TRUE
                """,
                (all_user_ids,),
            )
            for row in dbdict.fetchall():
                user_id = row["user_id"]
                legacy_key = tech_to_legacy.get(row["name"])
                if legacy_key and user_id in upgrades_map:
                    upgrades_map[user_id][legacy_key] = True

        # Preload all policies for all users at once
        policies_map = {}
        if all_user_ids:
            dbdict.execute(
                "SELECT user_id, education FROM policies WHERE user_id = ANY(%s)",
                (all_user_ids,),
            )
            for row in dbdict.fetchall():
                policies_map[row["user_id"]] = row["education"]

        # Preload all building data PER PROVINCE (not per user)
        # Each province has its own buildings since proInfra was per-province.
        buildings_map = {}  # province_id -> {building_name: quantity}
        if all_province_ids:
            dbdict.execute(
                """
                SELECT ub.province_id, bd.name, ub.quantity
                FROM user_buildings ub
                JOIN building_dictionary bd ON bd.building_id = ub.building_id
                WHERE ub.province_id = ANY(%s)
                """,
                (all_province_ids,),
            )
            for row in dbdict.fetchall():
                prov_id = row["province_id"]
                building_name = row["name"]
                quantity = row["quantity"]
                if prov_id not in buildings_map:
                    buildings_map[prov_id] = {}
                buildings_map[prov_id][building_name] = quantity

        # Preload all stats (gold) for all users at once
        stats_map = {}
        if all_user_ids:
            dbdict.execute(
                "SELECT id, gold FROM stats WHERE id = ANY(%s)", (all_user_ids,)
            )
            for row in dbdict.fetchall():
                stats_map[row["id"]] = row["gold"]

        # Preload all resources for all users at once (use user_economy)
        resources_map = {}  # user_id -> {resource_name: quantity}
        if all_user_ids:
            dbdict.execute(
                """
                SELECT ue.user_id, rd.name AS resource_name,
                       COALESCE(ue.quantity, 0) AS quantity
                FROM user_economy ue
                JOIN resource_dictionary rd ON rd.resource_id = ue.resource_id
                WHERE ue.user_id = ANY(%s)
                """,
                (all_user_ids,),
            )
            for row in dbdict.fetchall():
                user_id = row["user_id"]
                if user_id not in resources_map:
                    resources_map[user_id] = {}
                resources_map[user_id][row["resource_name"]] = row["quantity"]

        # Track resource DELTAS (changes) for atomic updates
        # This avoids race conditions with other tasks modifying resources
        resource_deltas = {uid: {} for uid in all_user_ids}

        # No blanket user_economy prefill here.
        # Resource writes below already use UPSERT and create missing rows lazily,
        # avoiding N(users*resources) conflict checks on every hourly run.
        # Track accumulated changes for batch updates at end
        gold_deductions = {}  # user_id -> total_deducted

        # Preload province data for effects + demographics tracking
        # (happiness, productivity, pollution, consumer_spending, energy)
        provinces_data = {}  # province_id -> {happiness, productivity, pollution,
        # consumer_spending, energy, ...}
        if all_province_ids:
            dbdict.execute(
                """
                SELECT id, happiness, productivity, pollution, consumer_spending,
                       energy, population,
                       COALESCE(pop_children, 0) AS pop_children,
                       COALESCE(pop_working, 0) AS pop_working,
                       COALESCE(pop_elderly, 0) AS pop_elderly
                FROM provinces WHERE id = ANY(%s)
            """,
                (all_province_ids,),
            )
            rows = dbdict.fetchall()
            if rows:
                for row in rows:
                    try:
                        prov_dict = dict(row)
                    except Exception:
                        # Row may be a tuple in some fakes; map by position
                        prov_dict = {
                            "id": row[0],
                            "happiness": row[1] if len(row) > 1 else 50,
                            "productivity": row[2] if len(row) > 2 else 50,
                            "pollution": row[3] if len(row) > 3 else 0,
                            "consumer_spending": row[4] if len(row) > 4 else 50,
                            "energy": 0,
                            "population": row[6] if len(row) > 6 else 0,
                            "pop_children": row[7] if len(row) > 7 else 0,
                            "pop_working": row[8] if len(row) > 8 else 0,
                            "pop_elderly": row[9] if len(row) > 9 else 0,
                        }
                    # Reset energy to 0 (will be built up by nuclear_reactors)
                    prov_dict["energy"] = 0
                    provinces_data[prov_dict["id"]] = prov_dict
            else:
                # Fall back to minimal default entries so we still reset energy
                for pid in all_province_ids:
                    provinces_data[pid] = {
                        "happiness": 50,
                        "productivity": 50,
                        "pollution": 0,
                        "consumer_spending": 50,
                        "energy": 0,
                        "population": 0,
                        "pop_children": 0,
                        "pop_working": 0,
                        "pop_elderly": 0,
                    }

        # PHASE 3: Pre-calculate workforce debuffs for all users once
        # (before processing provinces) using bulk-loaded data only.
        workforce_debuffs = {}
        if variables.FEATURE_PHASE3_WORKFORCE:
            # Preload demographics totals by user in one query
            dbdict.execute(
                """
                SELECT userId,
                       COALESCE(SUM(pop_working), 0) AS total_pop_working,
                       COALESCE(SUM(pop_elderly), 0) AS total_pop_elderly,
                       COALESCE(SUM(edu_none), 0) AS edu_none,
                       COALESCE(SUM(edu_highschool), 0) AS edu_highschool,
                       COALESCE(SUM(edu_college), 0) AS edu_college
                FROM provinces
                WHERE userId = ANY(%s)
                GROUP BY userId
                """,
                (all_user_ids,),
            )
            workforce_demo = {
                row["userid"]: {
                    "total_pop_working": int(row["total_pop_working"] or 0),
                    "total_pop_elderly": int(row["total_pop_elderly"] or 0),
                    "edu_none": int(row["edu_none"] or 0),
                    "edu_highschool": int(row["edu_highschool"] or 0),
                    "edu_college": int(row["edu_college"] or 0),
                }
                for row in dbdict.fetchall()
            }

            # Preload user building counts (all provinces) in one query
            dbdict.execute(
                """
                SELECT ub.user_id, bd.name, COALESCE(SUM(ub.quantity), 0) AS count
                FROM user_buildings ub
                JOIN building_dictionary bd ON bd.building_id = ub.building_id
                WHERE ub.user_id = ANY(%s)
                GROUP BY ub.user_id, bd.name
                """,
                (all_user_ids,),
            )
            user_building_counts = {}
            for row in dbdict.fetchall():
                uid = row["user_id"]
                if uid not in user_building_counts:
                    user_building_counts[uid] = {}
                user_building_counts[uid][row["name"]] = int(row["count"] or 0)

            building_matrices = variables.BUILDING_EMPLOYMENT_MATRICES
            for uid in all_user_ids:
                try:
                    demo = workforce_demo.get(
                        uid,
                        {
                            "total_pop_working": 0,
                            "total_pop_elderly": 0,
                            "edu_none": 0,
                            "edu_highschool": 0,
                            "edu_college": 0,
                        },
                    )

                    jobs_available = (
                        demo["edu_none"] + demo["edu_highschool"] + demo["edu_college"]
                    )
                    total_pop_working = demo["total_pop_working"]
                    total_pop_elderly = demo["total_pop_elderly"]

                    building_counts = user_building_counts.get(uid, {})
                    jobs_needed = 0
                    for building_name, matrix_data in building_matrices.items():
                        workers_per = matrix_data.get("worker_count", 0)
                        jobs_needed += workers_per * building_counts.get(
                            building_name, 0
                        )

                    unemployment_rate = 0.0
                    pension_ratio = 0.0
                    if total_pop_working > 0:
                        unemployment_rate = max(
                            0.0, 1.0 - (jobs_available / total_pop_working)
                        )
                        pension_ratio = total_pop_elderly / total_pop_working

                    if jobs_needed > 0:
                        employment_ratio = jobs_available / jobs_needed
                        efficiency_multiplier = max(
                            variables.PRODUCTION_EFFICIENCY_MIN, employment_ratio
                        )
                    else:
                        efficiency_multiplier = 1.0

                    happiness_penalty = 0
                    gold_penalty = 0
                    if unemployment_rate > variables.UNEMPLOYMENT_THRESHOLD:
                        happiness_penalty = variables.UNEMPLOYMENT_HAPPINESS_PENALTY
                    if pension_ratio > variables.PENSION_CRISIS_RATIO:
                        gold_penalty = variables.PENSION_CRISIS_GOLD_PENALTY

                    debuff_report = {
                        "jobs_needed": int(jobs_needed),
                        "jobs_available": int(jobs_available),
                        "unemployment_rate": float(unemployment_rate),
                        "pension_ratio": float(pension_ratio),
                        "efficiency_multiplier": float(efficiency_multiplier),
                        "happiness_penalty": int(happiness_penalty),
                        "gold_penalty": int(gold_penalty),
                    }
                    workforce_debuffs[uid] = debuff_report
                except Exception as e:
                    log_verbose(
                        f"apply_workforce_hiring_and_debuffs failed "
                        f"for user {uid}: {e}"
                    )
                    workforce_debuffs[uid] = {
                        "efficiency_multiplier": 1.0,
                        "happiness_penalty": 0,
                        "gold_penalty": 0,
                    }
        else:
            # Feature disabled: no efficiency reduction, no debuffs
            for uid in all_user_ids:
                workforce_debuffs[uid] = {
                    "efficiency_multiplier": 1.0,
                    "happiness_penalty": 0,
                    "gold_penalty": 0,
                }

        # Track happiness penalties per province (to apply after batch writes)
        happiness_penalties = {}  # province_id -> penalty_amount

        # Track education updates from aging to batch-write once
        education_deltas = {}  # province_id -> {edu_none, edu_highschool, edu_college}

        for province_id, user_id, land, productivity in infra_ids:
            # PHASE 3: Apply population aging using preloaded in-memory data.
            # This avoids per-province query/update churn during hourly revenue tick.
            if variables.FEATURE_PHASE3_WORKFORCE and province_id in provinces_data:
                try:
                    prov = provinces_data[province_id]
                    pop_children = int(prov.get("pop_children", 0) or 0)
                    pop_working = int(prov.get("pop_working", 0) or 0)
                    pop_elderly = int(prov.get("pop_elderly", 0) or 0)

                    policies = policies_map.get(user_id, []) or []
                    province_buildings = buildings_map.get(province_id, {})

                    elderly_death_rate = variables.DEMO_AGING_RATES["elderly_death"]
                    if variables.POLICY_UNIVERSAL_HEALTHCARE in policies:
                        elderly_death_rate *= (
                            variables.POLICY_HEALTHCARE_ELDERLY_DEATH_REDUCTION
                        )

                    elderly_deaths = int(round(pop_elderly * elderly_death_rate))
                    pop_elderly = max(0, pop_elderly - elderly_deaths)

                    working_to_elderly = int(
                        round(
                            pop_working
                            * variables.DEMO_AGING_RATES["working_to_elderly"]
                        )
                    )
                    pop_elderly += working_to_elderly
                    pop_working = max(0, pop_working - working_to_elderly)

                    graduation_rate = variables.DEMO_AGING_RATES["children_to_working"]
                    if variables.POLICY_MANDATORY_SCHOOLING in policies:
                        graduation_rate *= (
                            variables.POLICY_SCHOOLING_GRADUATION_MULTIPLIER
                        )

                    can_graduate = min(
                        pop_children, int(round(pop_children * graduation_rate))
                    )
                    school_buildings = int(
                        province_buildings.get("high_school", 0) or 0
                    ) + int(province_buildings.get("university", 0) or 0)
                    school_capacity = school_buildings * 100
                    graduates = (
                        min(can_graduate, school_capacity // 100)
                        if school_capacity > 0
                        else 0
                    )
                    non_graduates = can_graduate - graduates

                    if province_id not in education_deltas:
                        education_deltas[province_id] = {
                            "edu_none": 0,
                            "edu_highschool": 0,
                            "edu_college": 0,
                        }

                    if graduates > 0:
                        grad_priority = variables.EDUCATION_GRADUATION_PRIORITY
                        for edu_level in grad_priority:
                            if edu_level == "university":
                                education_deltas[province_id][
                                    "edu_college"
                                ] += graduates
                            elif edu_level == "high_school":
                                education_deltas[province_id][
                                    "edu_highschool"
                                ] += graduates
                            break

                    if non_graduates > 0:
                        education_deltas[province_id]["edu_none"] += non_graduates

                    pop_working += can_graduate
                    pop_children = max(0, pop_children - can_graduate)

                    prov["pop_children"] = pop_children
                    prov["pop_working"] = pop_working
                    prov["pop_elderly"] = pop_elderly
                except Exception as e:
                    log_verbose(
                        "In-memory population aging failed for province"
                        f" {province_id}: {e}"
                    )

            # Initialize tracking for this user
            if user_id not in gold_deductions:
                gold_deductions[user_id] = 0

            # Use preloaded upgrades instead of per-loop query
            upgrades = upgrades_map.get(user_id, {})

            # Use preloaded policies instead of per-loop query
            policies = policies_map.get(user_id, [])
            if policies is None:
                policies = []

            # Use preloaded buildings for THIS PROVINCE (not user-level)
            # Each province has its own set of buildings
            province_buildings = buildings_map.get(province_id, {})
            units = {}
            for col in columns:
                # Map column names directly to building names (they match)
                units[col] = province_buildings.get(col, 0)

            for unit in columns:
                unit_amount = units[unit]

                if unit_amount == 0:
                    continue

                unit_category = find_unit_category(unit)
                try:
                    # IMPORTANT: copy dicts so we don't mutate the module-level
                    # variables.NEW_INFRA constants.  Upgrades/policies modify
                    # these dicts in-place (e.g. eff["happiness"] *= 1.3) and
                    # without copies the values compound across iterations and
                    # across task runs, eventually producing astronomically wrong
                    # production/effect values.
                    effminus = dict(infra[unit].get("effminus", {}))
                    minus = dict(infra[unit].get("minus", {}))
                    operating_costs = infra[unit]["money"] * unit_amount
                    plus_amount = 0
                    plus_amount_multiplier = 1

                    # Apply productivity multiplier: 0.9% per productivity point
                    # At 50% productivity (neutral): 1.0x multiplier
                    # At 100% productivity: 1.45x multiplier (50 * 0.9% = 45%)
                    # At 0% productivity: 0.55x multiplier (-50 * 0.9% = -45%)
                    if productivity is not None:
                        productivity_multiplier = 1 + (
                            (productivity - 50)
                            * variables.DEFAULT_PRODUCTIVITY_PRODUCTION_MUTLIPLIER
                        )
                        plus_amount_multiplier *= productivity_multiplier

                    # CHEAPER MATERIALS
                    if unit_category == "industry" and upgrades.get("cheapermaterials"):
                        operating_costs *= 0.8
                    # ONLINE SHOPPING
                    if unit == "malls" and upgrades.get("onlineshopping"):
                        operating_costs *= 0.7

                    # INDUSTRIAL SUBSIDIES POLICY
                    if (
                        variables.POLICY_INDUSTRIAL_SUBSIDIES in policies
                        and unit in variables.POLICY_SUBSIDIES_AFFECTED_BUILDINGS
                    ):
                        operating_costs *= variables.POLICY_SUBSIDIES_UPKEEP_REDUCTION

                    # Use preloaded gold and track deductions
                    # (instead of per-building SELECT+UPDATE)
                    current_money = stats_map.get(user_id, 0) - gold_deductions.get(
                        user_id, 0
                    )

                    operating_costs = int(operating_costs)

                    # Boolean for whether a player has enough resources, energy,
                    # money to power his building
                    has_enough_stuff = {"status": True, "issues": []}

                    if current_money < operating_costs:
                        log_verbose(
                            f"Skip {unit} province {province_id}: not enough money"
                        )
                        has_enough_stuff["status"] = False
                        has_enough_stuff["issues"].append("money")
                    else:
                        # Track deduction for batch update at end
                        gold_deductions[user_id] = (
                            gold_deductions.get(user_id, 0) + operating_costs
                        )

                    # Use tracked energy in provinces_data instead of
                    # per-building SELECT
                    if unit in energy_consumers:
                        prov_data = provinces_data.get(province_id, {})
                        current_energy = prov_data.get("energy", 0)

                        new_energy = (
                            current_energy - unit_amount
                        )  # Each unit consumes 1 energy

                        if new_energy < 0:
                            has_enough_stuff["status"] = False
                            has_enough_stuff["issues"].append("energy")
                            new_energy = 0

                        # Track energy in provinces_data for batch update
                        if province_id in provinces_data:
                            provinces_data[province_id]["energy"] = new_energy

                    # Use preloaded resources instead of per-building queries
                    resources = resources_map.get(user_id, {})
                    # Resources is now a dict of resource_name -> quantity
                    # (no fallback query needed, all loaded upfront)

                    for resource, amount in minus.items():
                        amount *= unit_amount
                        current_resource = resources.get(resource, 0)
                        # Account for any pending deltas in this run
                        pending_delta = resource_deltas.get(user_id, {}).get(
                            resource, 0
                        )
                        effective_current = current_resource + pending_delta

                        # AUTOMATION INTEGRATION
                        if unit == "component_factories" and upgrades.get(
                            "automationintegration"
                        ):
                            amount *= 0.75
                        # LARGER FORGES
                        if unit == "steel_mills" and upgrades.get("largerforges"):
                            amount *= 0.7

                        new_resource = effective_current - amount

                        if new_resource < 0:
                            has_enough_stuff["status"] = False
                            has_enough_stuff["issues"].append(resource)
                            log_verbose(
                                (
                                    "F | USER: %s | PROVINCE: %s | %s (%s) | "
                                    "Failed to minus %s of %s (%s)"
                                )
                                % (
                                    user_id,
                                    province_id,
                                    unit,
                                    unit_amount,
                                    amount,
                                    resource,
                                    effective_current,
                                )
                            )
                        else:
                            # Track delta for atomic batch update
                            if user_id not in resource_deltas:
                                resource_deltas[user_id] = {}
                            resource_deltas[user_id][resource] = (
                                resource_deltas[user_id].get(resource, 0) - amount
                            )
                            log_verbose(
                                (
                                    "S | MINUS | USER: %s | PROVINCE: %s | %s (%s) | "
                                    "%s %s delta=-%s"
                                )
                                % (
                                    user_id,
                                    province_id,
                                    unit,
                                    unit_amount,
                                    resource,
                                    effective_current,
                                    amount,
                                )
                            )

                    if not has_enough_stuff["status"]:
                        issues_str = ", ".join(has_enough_stuff["issues"])
                        log_verbose(
                            "F | USER: %s | PROVINCE: %s | %s (%s) | Not enough %s"
                            % (user_id, province_id, unit, unit_amount, issues_str)
                        )
                        continue

                    plus = dict(infra[unit].get("plus", {}))

                    # BETTER ENGINEERING
                    if unit == "nuclear_reactors" and upgrades.get("betterengineering"):
                        plus["energy"] += 6

                    eff = dict(infra[unit].get("eff", {}))

                    if unit == "universities" and 3 in policies:
                        eff["productivity"] *= 1.10
                        eff["happiness"] *= 1.10

                    if unit == "hospitals":
                        if upgrades.get("nationalhealthinstitution"):
                            eff["happiness"] *= 1.3
                            eff["happiness"] = int(eff["happiness"])

                    if unit == "monorails":
                        if upgrades.get("highspeedrail"):
                            eff["productivity"] *= 1.2
                            eff["productivity"] = int(eff["productivity"])

                    """
                    print(f"Unit: {unit}")
                    print(f"Add {plus_amount} to {plus_resource}")
                    print(f"Remove ${operating_costs} as operating costs")
                    print(f"\n")
                    """
                    if unit == "bauxite_mines" and upgrades.get("strongerexplosives"):
                        # TODO: fix this plus_amount variable
                        plus_amount_multiplier += 0.45

                    if unit == "farms":
                        if upgrades.get("advancedmachinery"):
                            plus_amount_multiplier += 0.5

                        plus_amount += int(
                            land * variables.LAND_FARM_PRODUCTION_ADDITION
                        )

                    # PHASE 3: Apply workforce efficiency multiplier
                    # (reduces production if understaffed)
                    debuff_info = workforce_debuffs.get(
                        user_id, {"efficiency_multiplier": 1.0}
                    )
                    plus_amount_multiplier *= debuff_info.get(
                        "efficiency_multiplier", 1.0
                    )

                    # Function for _plus
                    for resource, amount in plus.items():
                        amount += plus_amount
                        amount *= unit_amount
                        amount *= plus_amount_multiplier
                        # Normalize production to integer units so we don't
                        # persist fractional resources (e.g., 0.5 rations).
                        # Use ceil to avoid losing tiny outputs.
                        amount = math.ceil(amount)
                        if resource in province_resources:
                            # Use preloaded province data instead of per-building SELECT
                            prov_data = provinces_data.get(province_id, {})
                            current_plus_resource = prov_data.get(resource, 0)

                            # Adding resource
                            new_resource_number = current_plus_resource + amount

                            if (
                                resource in percentage_based
                                and new_resource_number > 100
                            ):
                                new_resource_number = 100
                            if new_resource_number < 0:
                                new_resource_number = 0

                            # Update local cache for batch write later
                            if province_id in provinces_data:
                                provinces_data[province_id][
                                    resource
                                ] = new_resource_number
                            msg = (
                                f"S | PLUS | U:{user_id} | P:{province_id} | {unit} "
                                f"({unit_amount}) | ADDING | {resource} | {amount}"
                            )
                            log_verbose(msg)

                        elif resource in user_resources:
                            # Track delta for atomic batch update
                            if user_id not in resource_deltas:
                                resource_deltas[user_id] = {}
                            resource_deltas[user_id][resource] = (
                                resource_deltas[user_id].get(resource, 0) + amount
                            )
                            msg = (
                                f"S | PLUS | U:{user_id} | P:{province_id} | "
                                f"{unit} ({unit_amount}) | {resource} | +{amount}"
                            )
                            log_verbose(msg)

                    # Function for completing an effect (adding pollution, etc)
                    def do_effect(
                        eff_name,
                        eff_amount,
                        sign,
                        province_id=province_id,
                        unit_category=unit_category,
                        upgrades=upgrades,
                        unit=unit,
                        policies=policies,
                        percentage_based=percentage_based,
                    ):
                        # Use preloaded province data instead of per-building SELECT
                        prov_data = provinces_data.get(province_id, {})
                        current_effect = prov_data.get(eff_name, 0)

                        # GOVERNMENT REGULATION
                        if (
                            unit_category == "retail"
                            and upgrades.get("governmentregulation")
                            and eff_name == "pollution"
                            and sign == "+"
                        ):
                            eff_amount *= 0.75

                        # INDUSTRIAL SUBSIDIES POLICY
                        if (
                            variables.POLICY_INDUSTRIAL_SUBSIDIES in policies
                            and unit in variables.POLICY_SUBSIDIES_AFFECTED_BUILDINGS
                            and eff_name == "pollution"
                            and sign == "+"
                        ):
                            eff_amount *= (
                                variables.POLICY_SUBSIDIES_POLLUTION_MULTIPLIER
                            )

                        # Round effect amounts to nearest integer instead of always
                        # rounding up. Using `round` prevents an upward bias when
                        # fractional multipliers (such as government regulation) are
                        # applied which could otherwise cause small fractional
                        # reductions to become full +1 increases via `ceil`, leading
                        # to oscillation near high pollution values.
                        eff_amount = int(round(eff_amount))

                        if sign == "+":
                            new_effect = current_effect + eff_amount
                        elif sign == "-":
                            new_effect = current_effect - eff_amount

                        if eff_name in percentage_based:
                            if new_effect > 100:
                                new_effect = 100
                            if new_effect < 0:
                                new_effect = 0
                        else:
                            if new_effect < 0:
                                new_effect = 0

                        # Update local cache for batch write later
                        if province_id in provinces_data:
                            provinces_data[province_id][eff_name] = new_effect

                    for effect, amount in eff.items():
                        amount *= unit_amount
                        do_effect(effect, amount, "+")

                    for effect, amount in effminus.items():
                        amount *= unit_amount
                        do_effect(effect, amount, "-")

                except Exception as e:
                    # The building processing loop only modifies in-memory
                    # dicts (resource_deltas, provinces_data, gold_deductions).
                    # A conn.rollback() here was harmful: it rolled back
                    # earlier DB writes (like user_economy row ensures) and
                    # could leave the connection in a bad state for subsequent
                    # batch writes.  Just log the error and continue.
                    print(
                        f"ERROR processing building {unit} province "
                        f"{province_id} user {user_id}: {e}"
                    )
                    handle_exception(e)
                    continue

            # PHASE 3: Track happiness penalty from unemployment debuff
            # (to apply after batch writes)
            debuff_info = workforce_debuffs.get(user_id, {"happiness_penalty": 0})
            unemployment_penalty = debuff_info.get("happiness_penalty", 0)
            if unemployment_penalty > 0 and province_id in provinces_data:
                # Reduce happiness by unemployment penalty
                current_hap = provinces_data[province_id].get("happiness", 50)
                new_hap = max(0, current_hap - unemployment_penalty)
                provinces_data[province_id]["happiness"] = new_hap
                # Track for logging
                happiness_penalties[province_id] = unemployment_penalty

            processed += 1

        # ============ APPLY POLICY HAPPINESS BONUSES ============
        # Build user->provinces mapping from infra_ids
        user_provinces = {}
        for province_id, user_id, _, _ in infra_ids:
            if user_id not in user_provinces:
                user_provinces[user_id] = []
            user_provinces[user_id].append(province_id)

        # Apply happiness bonuses from policies before batch write
        for user_id, prov_ids in user_provinces.items():
            if user_id not in policies_map:
                continue
            policies = policies_map[user_id]

            # Universal Healthcare: +5 happiness per province
            if variables.POLICY_UNIVERSAL_HEALTHCARE in policies:
                for province_id in prov_ids:
                    if province_id in provinces_data:
                        current_hap = provinces_data[province_id].get("happiness", 50)
                        new_hap = min(
                            100,
                            current_hap + variables.POLICY_HEALTHCARE_HAPPINESS_BONUS,
                        )
                        provinces_data[province_id]["happiness"] = new_hap

            # Mandatory Schooling: +3 happiness per province
            if variables.POLICY_MANDATORY_SCHOOLING in policies:
                for province_id in prov_ids:
                    if province_id in provinces_data:
                        current_hap = provinces_data[province_id].get("happiness", 50)
                        new_hap = min(
                            100,
                            current_hap + variables.POLICY_SCHOOLING_HAPPINESS_BONUS,
                        )
                        provinces_data[province_id]["happiness"] = new_hap

            # Rationing Program: -10 happiness per province
            if variables.POLICY_RATIONING_PROGRAM in policies:
                for province_id in prov_ids:
                    if province_id in provinces_data:
                        current_hap = provinces_data[province_id].get("happiness", 50)
                        new_hap = max(
                            0,
                            current_hap - variables.POLICY_RATIONING_HAPPINESS_PENALTY,
                        )
                        provinces_data[province_id]["happiness"] = new_hap

        # ============ BATCH WRITE ALL ACCUMULATED CHANGES ============
        # PHASE 3: Apply pension crisis gold penalties
        pension_penalties = {}  # user_id -> penalty_amount
        if variables.FEATURE_PHASE3_WORKFORCE:
            for user_id, debuff_info in workforce_debuffs.items():
                gold_penalty = debuff_info.get("gold_penalty", 0)
                if gold_penalty > 0:
                    gold_deductions[user_id] = (
                        gold_deductions.get(user_id, 0) + gold_penalty
                    )
                    pension_penalties[user_id] = gold_penalty

        # Write all gold deductions in batch
        try:
            if gold_deductions:
                gold_updates = [
                    (amount, user_id)
                    for user_id, amount in gold_deductions.items()
                    if amount > 0
                ]
                if gold_updates:
                    execute_batch(
                        db,
                        "UPDATE stats SET gold = gold - %s WHERE id = %s",
                        gold_updates,
                        page_size=100,
                    )
                    log_verbose(f"Batch updated gold for {len(gold_updates)} users")
                    if pension_penalties:
                        log_verbose(
                            f"Applied pension crisis penalties "
                            f"to {len(pension_penalties)} users"
                        )
        except Exception as e:
            conn.rollback()
            handle_exception(e)

        # Write all province changes in batch
        # (happiness, productivity, pollution, consumer_spending, energy, rations)
        try:
            if provinces_data:
                # Snapshot pollution before we apply batch updates so we can detect
                # unusually large changes and emit a best-effort metric for
                # observability. Keep threshold conservative to avoid noise.
                initial_province_pollution = {
                    pid: data.get("pollution", 0)
                    for pid, data in provinces_data.items()
                }

                province_updates = []
                for pid, data in provinces_data.items():
                    # Emit a metric if pollution changes by >= 6 percentage points
                    try:
                        new_poll = min(100, max(0, data.get("pollution", 0)))
                        old_poll = initial_province_pollution.get(pid, 0)
                        delta = new_poll - old_poll
                        if abs(delta) >= 6:
                            try:
                                from helpers import record_task_metric

                                record_task_metric(
                                    "province_pollution_delta", float(delta)
                                )
                            except Exception:
                                pass
                    except Exception:
                        pass

                    pop_c = max(0, int(data.get("pop_children", 0) or 0))
                    pop_w = max(0, int(data.get("pop_working", 0) or 0))
                    pop_e = max(0, int(data.get("pop_elderly", 0) or 0))

                    province_updates.append(
                        (
                            min(100, max(0, data.get("happiness", 50))),
                            min(100, max(0, data.get("productivity", 50))),
                            min(100, max(0, data.get("pollution", 0))),
                            min(100, max(0, data.get("consumer_spending", 50))),
                            data.get("energy", 0),
                            pop_c + pop_w + pop_e,
                            pop_c,
                            pop_w,
                            pop_e,
                            pid,
                        )
                    )
                if province_updates:
                    try:
                        execute_batch(
                            db,
                            """
                            UPDATE provinces SET
                                happiness = %s,
                                productivity = %s,
                                pollution = %s,
                                consumer_spending = %s,
                                energy = %s,
                                population = %s,
                                pop_children = %s,
                                pop_working = %s,
                                pop_elderly = %s
                            WHERE id = %s
                        """,
                            province_updates,
                            page_size=100,
                        )
                    except AttributeError:
                        for params in province_updates:
                            db.execute(
                                """
                                UPDATE provinces SET
                                    happiness = %s,
                                    productivity = %s,
                                    pollution = %s,
                                    consumer_spending = %s,
                                    energy = %s,
                                    population = %s,
                                    pop_children = %s,
                                    pop_working = %s,
                                    pop_elderly = %s
                                WHERE id = %s
                            """,
                                params,
                            )
                    log_verbose(f"Batch updated {len(province_updates)} provinces")
        except Exception as e:
            conn.rollback()
            handle_exception(e)

        # Batch apply education deltas from aging
        try:
            if education_deltas:
                edu_updates = [
                    (
                        delta.get("edu_none", 0),
                        delta.get("edu_highschool", 0),
                        delta.get("edu_college", 0),
                        pid,
                    )
                    for pid, delta in education_deltas.items()
                    if (
                        delta.get("edu_none", 0)
                        or delta.get("edu_highschool", 0)
                        or delta.get("edu_college", 0)
                    )
                ]
                if edu_updates:
                    execute_batch(
                        db,
                        """
                        UPDATE provinces
                        SET edu_none = COALESCE(edu_none, 0) + %s,
                            edu_highschool = COALESCE(edu_highschool, 0) + %s,
                            edu_college = COALESCE(edu_college, 0) + %s
                        WHERE id = %s
                        """,
                        edu_updates,
                        page_size=100,
                    )
        except Exception as e:
            conn.rollback()
            handle_exception(e)

        # Write all resource changes atomically using deltas
        # This prevents race conditions with other tasks (e.g., population_growth)
        try:
            if resource_deltas:
                # Flatten resource_deltas into (user_id, resource_name, delta) tuples
                resource_updates = []
                for user_id, deltas in resource_deltas.items():
                    if not deltas:
                        continue
                    for resource_name, delta in deltas.items():
                        if delta != 0:
                            resource_updates.append((user_id, resource_name, delta))

                if resource_updates:
                    # Get all resource_ids
                    resource_names = list(set(r[1] for r in resource_updates))
                    dbdict.execute(
                        "SELECT name, resource_id FROM resource_dictionary "
                        "WHERE name = ANY(%s)",
                        (resource_names,),
                    )
                    resource_id_map = {
                        row["name"]: row["resource_id"] for row in dbdict.fetchall()
                    }

                    # Build final batch: (user_id, resource_id, insert_qty, raw_delta)
                    # We pass the delta TWICE: once clamped for INSERT (new rows
                    # start at >= 0) and once raw for the UPDATE (so negative
                    # deltas actually subtract from the existing quantity).
                    batch_values = [
                        (uid, resource_id_map[rname], max(0, delta), delta)
                        for uid, rname, delta in resource_updates
                        if rname in resource_id_map
                    ]

                    if batch_values:
                        # Upsert into user_economy (insert if missing, else += delta)
                        execute_batch(
                            db,
                            """
                            INSERT INTO user_economy (user_id, resource_id, quantity)
                            VALUES (%s, %s, %s)
                            ON CONFLICT (user_id, resource_id)
                            DO UPDATE SET quantity = GREATEST(
                                0, user_economy.quantity + %s
                            )
                            """,
                            batch_values,
                            page_size=200,
                        )
                        log_verbose(
                            f"Upserted resources for {len(batch_values)} "
                            "user+resource pairs"
                        )

                        # Invalidate resource cache for affected users
                        # so UI reflects updated values immediately (best-effort)
                        try:
                            from database import invalidate_user_cache

                            unique_users = set(bv[0] for bv in batch_values)
                            for user_id in unique_users:
                                try:
                                    invalidate_user_cache(user_id)
                                except Exception:
                                    pass
                        except Exception:
                            pass
        except Exception as e:
            conn.rollback()
            handle_exception(e)

        # Final commit
        try:
            try:
                conn.commit()
            except AttributeError:
                # Fake connection used in tests may not implement commit
                pass
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
        duration = time.perf_counter() - start_time

        # Emit metric for generate_province_revenue
        try:
            from helpers import record_task_metric

            record_task_metric("generate_province_revenue", duration)
        except Exception:
            pass

        # Optional verbose logging for diagnostics. When VERBOSE_REVENUE_LOGS is
        # enabled, we emit expected gross production for resources per user so
        # operations teams can investigate discrepancies between theoretical
        # production and actual DB deltas observed after the task runs.
        if VERBOSE_REVENUE_LOGS:
            try:
                import countries

                for uid in all_user_ids:
                    try:
                        rev = countries.get_revenue(uid)
                        exp = rev.get("gross", {})
                        coal_exp = exp.get("coal", 0)
                        lumber_exp = exp.get("lumber", 0)
                        if coal_exp or lumber_exp:
                            log_verbose(
                                (
                                    f"Revenue expected for user {uid}: "
                                    f"coal={coal_exp}, lumber={lumber_exp}"
                                )
                            )
                    except Exception as e:
                        log_verbose(
                            f"Failed to compute expected revenue for user {uid}: {e}"
                        )
            except Exception as e:
                log_verbose(f"Verbose revenue logging failed: {e}")

        print(
            f"generate_province_revenue: processed {processed} provinces in "
            f"{duration:.2f}s (skipped={skipped_for_lock})"
        )

        # Update progress cursor to the last processed province id so subsequent
        # runs continue from the next id and avoid reprocessing large sets
        try:
            if all_province_ids:
                last_processed_pid = max(all_province_ids)
                db.execute(
                    "UPDATE task_cursors SET last_id=%s WHERE task_name=%s",
                    (last_processed_pid, "generate_province_revenue"),
                )
                try:
                    conn.commit()
                except Exception:
                    pass
        except Exception as e:
            print(f"Failed to update task cursor for generate_province_revenue: {e}")

        try:
            release_pg_advisory_lock(conn, 9002)
        except Exception:
            pass


def war_reparation_tax():
    from database import get_db_connection
    from psycopg2.extras import RealDictCursor

    with get_db_connection() as conn:
        db = conn.cursor()
        dbdict = conn.cursor(cursor_factory=RealDictCursor)
        db.execute(
            "SELECT war_id, peace_date, attacker_id, attacker_morale, "
            "defender_id, defender_morale FROM wars WHERE (peace_date IS NOT "
            "NULL) AND (peace_offer_id IS NULL)"
        )
        truces = db.fetchall()

        for state in truces:
            war_id, peace_date, attacker, a_morale, defender, d_morale = state

            # Remove peace records older than one week (604800 seconds)
            if peace_date < (time.time() - 604800):
                db.execute("DELETE FROM wars WHERE war_id=%s", (war_id,))

            # Transfer resources to attacker (winner)
            else:
                if d_morale <= 0:
                    winner = attacker
                    loser = defender
                else:
                    winner = defender
                    loser = attacker

                eco = Economy(loser)

                # OPTIMIZATION: Fetch all resources and war_type in ONE query
                # each instead of 30 queries
                dbdict.execute(
                    """
                    SELECT rd.name AS resource_name,
                           COALESCE(ue.quantity, 0) AS quantity
                    FROM resource_dictionary rd
                    LEFT JOIN user_economy ue
                        ON ue.resource_id = rd.resource_id
                       AND ue.user_id = %s
                    WHERE rd.name = ANY(%s)
                    """,
                    (loser, Economy.resources),
                )
                resource_amounts = {
                    row["resource_name"]: row["quantity"] for row in dbdict.fetchall()
                }

                db.execute("SELECT war_type FROM wars WHERE war_id=%s", (war_id,))
                war_type = db.fetchone()

                for resource in Economy.resources:
                    resource_amount = resource_amounts.get(resource, 0) or 0

                    # This condition lower or doesn't give reparation_tax at all
                    # NOTE: for now it lowers to only 5% (the basic is 20%)
                    if war_type == "Raze":
                        eco.transfer_resources(
                            resource, resource_amount * (1 / 20), winner
                        )
                    else:
                        # transfer 20% of all resource
                        # (TODO: implement if and alliance won how to give it)
                        eco.transfer_resources(
                            resource, resource_amount * (1 / 5), winner
                        )


def _run_with_deadlock_retries(fn, label: str, max_retries: int = 3):
    """Run DB-heavy function with retries on Postgres deadlocks.
    Retries on transient errors as well."""
    import random
    from psycopg2 import errors as pg_errors

    attempt = 0
    while True:
        try:
            return fn()
        except pg_errors.DeadlockDetected as e:
            attempt += 1
            if attempt > max_retries:
                print(
                    f"{label}: exceeded deadlock retries ({max_retries}). "
                    f"Last error: {e}"
                )
                raise
            backoff = 0.2 * attempt + random.uniform(0, 0.2)
            print(
                f"{label}: deadlock detected, retrying in {backoff:.2f}s "
                f"(attempt {attempt}/{max_retries})"
            )
            try:
                time.sleep(backoff)
            except Exception:
                pass
            continue
        except psycopg2.InterfaceError as e:
            # Connection was closed (likely due to forked workers sharing pool).
            # Attempt pool reset then retry once per attempt.
            print(f"{label}: InterfaceError: {e}. Reinitializing pool and retrying.")
            try:
                from database import db_pool

                try:
                    db_pool.close_all()
                except Exception:
                    pass
            except Exception:
                pass
            attempt += 1
            if attempt > max_retries:
                print(
                    f"{label}: exceeded interface error retries ({max_retries}). "
                    f"Last error: {e}"
                )
                raise
            try:
                time.sleep(0.1 * attempt)
            except Exception:
                pass
            continue


# Leader-only decorator to avoid duplicate scheduled task executions
# when multiple beat/scheduler instances are active (e.g., autoscaling).
# It attempts to acquire a short-lived Redis lock and skips execution if
# another instance holds the lock.


def leader_only(ttl_seconds=60, key_prefix="task_lock"):
    def decorator(fn):
        def wrapper(*args, **kwargs):
            if redis is None:
                # If redis not available, fall back to running the task
                return fn(*args, **kwargs)
            try:
                url = os.getenv("REDIS_URL") or os.getenv("REDIS_PUBLIC_URL")
                if not url:
                    return fn(*args, **kwargs)
                parsed = urllib.parse.urlparse(url)
                r = redis.Redis(
                    host=parsed.hostname or "localhost",
                    port=parsed.port or 6379,
                    password=parsed.password,
                )
                key = f"{key_prefix}:{fn.__name__}"
                got = r.set(key, "1", nx=True, ex=ttl_seconds)
                if not got:
                    print(f"{fn.__name__}: skipped (leader lock not acquired)")
                    return
                try:
                    return fn(*args, **kwargs)
                finally:
                    try:
                        r.delete(key)
                    except Exception:
                        pass
            except Exception as e:
                print(f"leader_only decorator error for {fn.__name__}: {e}")
                # If anything goes wrong, run the task to avoid data loss
                return fn(*args, **kwargs)

        wrapper.__name__ = fn.__name__
        wrapper.__doc__ = fn.__doc__
        return wrapper

    return decorator


@celery.task()
@leader_only(ttl_seconds=300)
def task_population_growth():
    _run_with_deadlock_retries(population_growth, "population_growth")


@celery.task()
@leader_only(ttl_seconds=300)
def task_tax_income():
    tax_income()


@celery.task()
@leader_only(ttl_seconds=300)
def task_generate_province_revenue():
    _run_with_deadlock_retries(generate_province_revenue, "generate_province_revenue")


# Runs once a day
# Transfer X% of all resources (could depends on conditions like Raze war_type)
# to the winner side after a war


@celery.task()
@leader_only(ttl_seconds=300)
def task_war_reparation_tax():
    war_reparation_tax()


@celery.task()
@leader_only(ttl_seconds=300)
def task_manpower_increase():
    from database import get_db_connection
    from psycopg2.extras import execute_batch, RealDictCursor

    with get_db_connection() as conn:
        db = conn.cursor()
        dbdict = conn.cursor(cursor_factory=RealDictCursor)

        db.execute("SELECT id FROM users")
        user_ids = [row[0] for row in db.fetchall()]

        if not user_ids:
            return

        # Bulk load population totals per user
        pop_map = {}
        dbdict.execute(
            """
            SELECT userid, SUM(population) as total_pop
            FROM provinces
            WHERE userid = ANY(%s)
            GROUP BY userid
        """,
            (user_ids,),
        )
        for row in dbdict.fetchall():
            pop_map[row["userid"]] = row["total_pop"]

        # Bulk load current manpower from stats
        manpower_map = {}
        dbdict.execute(
            (
                "SELECT id, COALESCE(manpower, 0) AS manpower "
                "FROM stats WHERE id = ANY(%s)"
            ),
            (user_ids,),
        )
        for row in dbdict.fetchall():
            manpower_map[row["id"]] = row["manpower"]

        # Prepare batch updates
        manpower_updates = []
        for user_id in user_ids:
            population = pop_map.get(user_id)
            if not population:
                continue

            capable_population = population * 0.2
            army_tradition = 0.5  # Increased for faster regeneration
            produced_manpower = int(capable_population * army_tradition)

            manpower = manpower_map.get(user_id, 0)
            if manpower + produced_manpower >= population:
                produced_manpower = 0

            if produced_manpower > 0:
                manpower_updates.append((produced_manpower, user_id))

        # Batch update all manpower at once
        if manpower_updates:
            execute_batch(
                db,
                "UPDATE stats SET manpower = manpower + %s WHERE id=%s",
                manpower_updates,
                page_size=100,
            )
        conn.commit()


def backfill_missing_resources():
    from database import get_db_connection
    from psycopg2.extras import execute_batch, RealDictCursor

    # Clean up stale user-linked rows first so backfill never tries to
    # operate around orphaned records from deleted users.
    cleanup_orphan_user_rows()

    with get_db_connection() as conn:
        db = conn.cursor()
        dbdict = conn.cursor(cursor_factory=RealDictCursor)

        # Find users missing user_economy rows (users who don't have all resource_ids)
        dbdict.execute(
            """
            SELECT DISTINCT u.id
            FROM users u
            CROSS JOIN resource_dictionary rd
            LEFT JOIN user_economy ue
                ON ue.user_id = u.id
               AND ue.resource_id = rd.resource_id
            WHERE ue.user_id IS NULL
            """
        )
        missing_users = {row["id"] for row in dbdict.fetchall()}
        if not missing_users:
            return

        # Get all resource_ids
        dbdict.execute("SELECT resource_id FROM resource_dictionary")
        resource_ids = [row["resource_id"] for row in dbdict.fetchall()]

        # Build (user_id, resource_id, 0) tuples for all missing combinations
        params = [
            (user_id, resource_id, 0)
            for user_id in missing_users
            for resource_id in resource_ids
        ]

        try:
            execute_batch(
                db,
                "INSERT INTO user_economy (user_id, resource_id, quantity) "
                "VALUES (%s, %s, %s) ON CONFLICT (user_id, resource_id) DO NOTHING",
                params,
            )
            print(f"Backfilled user_economy for {len(missing_users)} users")
        except Exception as e:
            handle_exception(e)


def cleanup_orphan_user_rows():
    """Delete rows that reference users that no longer exist.

    This keeps user-scoped tables consistent and prevents FK violations in
    subsequent batch upserts (e.g., user_economy backfills).
    """
    from database import get_db_connection

    with get_db_connection() as conn:
        if not try_pg_advisory_lock(conn, 9006, "cleanup_orphan_user_rows"):
            return

        db = conn.cursor()
        deleted = {}
        try:
            cleanup_statements = [
                (
                    "user_economy",
                    """
                    DELETE FROM user_economy ue
                    WHERE NOT EXISTS (
                        SELECT 1 FROM users u WHERE u.id = ue.user_id
                    )
                    """,
                ),
                (
                    "user_buildings",
                    """
                    DELETE FROM user_buildings ub
                    WHERE NOT EXISTS (
                        SELECT 1 FROM users u WHERE u.id = ub.user_id
                    )
                    """,
                ),
                (
                    "user_military",
                    """
                    DELETE FROM user_military um
                    WHERE NOT EXISTS (
                        SELECT 1 FROM users u WHERE u.id = um.user_id
                    )
                    """,
                ),
                (
                    "stats",
                    """
                    DELETE FROM stats s
                    WHERE NOT EXISTS (
                        SELECT 1 FROM users u WHERE u.id = s.id
                    )
                    """,
                ),
                (
                    "provinces",
                    """
                    DELETE FROM provinces p
                    WHERE NOT EXISTS (
                        SELECT 1 FROM users u WHERE u.id = p.userid
                    )
                    """,
                ),
            ]

            for label, sql in cleanup_statements:
                db.execute(sql)
                deleted[label] = db.rowcount

            conn.commit()

            total_deleted = sum(deleted.values())
            if total_deleted > 0:
                print(
                    "cleanup_orphan_user_rows: removed "
                    f"{total_deleted} orphan rows "
                    f"(details: {deleted})"
                )
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            handle_exception(e)
        finally:
            try:
                release_pg_advisory_lock(conn, 9006)
            except Exception:
                pass


# Bot market offers configuration
BOT_USER_ID = 9999  # Market Bot account
BOT_OFFERS = [
    # (type, resource, amount, price)
    # Prices calibrated to player market rates (CG ~1000-2200, rations ~200-500)
    ("sell", "consumer_goods", 50000, 1500),  # 50k consumer goods @ 1,500 gold
    ("sell", "rations", 100000, 300),  # 100k rations @ 300 gold
    ("sell", "steel", 20000, 4000),  # 20k steel @ 4,000 gold
    ("sell", "aluminium", 10000, 3000),  # 10k aluminium @ 3,000 gold
    ("sell", "components", 5000, 8000),  # 5k components @ 8,000 gold
    ("buy", "coal", 50000, 80),  # buy 50k coal @ 80 gold
    ("buy", "iron", 50000, 120),  # buy 50k iron @ 120 gold
    ("buy", "lumber", 50000, 60),  # buy 50k lumber @ 60 gold
    ("buy", "oil", 50000, 150),  # buy 50k oil @ 150 gold
    ("buy", "copper", 50000, 100),  # buy 50k copper @ 100 gold
    ("buy", "bauxite", 50000, 90),  # buy 50k bauxite @ 90 gold
]


def refresh_bot_offers():
    """Delete old bot offers and create fresh ones for essential resources."""
    from database import get_db_connection

    with get_db_connection() as conn:
        db = conn.cursor()

        for offer_type, resource, amount, price in BOT_OFFERS:
            # Delete existing bot offers for this resource/type combo
            db.execute(
                "DELETE FROM offers WHERE user_id = %s AND resource = %s AND type = %s",
                (BOT_USER_ID, resource, offer_type),
            )

            # Insert fresh offer
            db.execute(
                "INSERT INTO offers (user_id, type, resource, amount, price) "
                "VALUES (%s, %s, %s, %s, %s)",
                (BOT_USER_ID, offer_type, resource, amount, price),
            )

        print(f"Bot offers refreshed: {len(BOT_OFFERS)} offers created")


@celery.task
@leader_only(ttl_seconds=300)
def task_refresh_bot_offers():
    """Celery task to refresh bot market offers every 5 minutes."""
    _run_with_deadlock_retries(refresh_bot_offers, "refresh_bot_offers")


@celery.task()
@leader_only(ttl_seconds=300)
def task_backfill_missing_resources():
    _run_with_deadlock_retries(backfill_missing_resources, "backfill_missing_resources")


@celery.task()
@leader_only(ttl_seconds=300)
def task_cleanup_orphan_user_rows():
    _run_with_deadlock_retries(cleanup_orphan_user_rows, "cleanup_orphan_user_rows")


@celery.task(name="tasks.task_cleanup_old_spyinfo")
def task_cleanup_old_spyinfo():
    """Remove spyinfo rows older than 7 days. Runs daily via beat."""
    import time as _time
    from database import get_db_cursor

    cutoff = int(_time.time()) - 86400 * 7
    try:
        with get_db_cursor() as db:
            db.execute("DELETE FROM spyinfo WHERE date < %s", (cutoff,))
        print(f"[cleanup_old_spyinfo] Deleted spyinfo rows older than cutoff={cutoff}")
    except Exception as exc:
        print(f"[cleanup_old_spyinfo] Error: {exc}")


# =============================================================================
# TRADE AGREEMENTS - Automatic recurring trades
# =============================================================================


def execute_due_trade_agreements():
    """Find and execute all trade agreements that are due."""
    import time
    import traceback
    from trade_agreements import execute_trade_agreement
    from database import get_db_connection

    start_time = time.perf_counter()

    with get_db_connection() as conn:
        db = conn.cursor()

        # Advisory lock to prevent concurrent execution (lock ID 9004)
        db.execute("SELECT pg_try_advisory_lock(9004)")
        got_lock = db.fetchone()[0]
        if not got_lock:
            print(
                "execute_trade_agreements: another run is already in progress, skipping"
            )
            return

        try:
            # Check last run time to prevent duplicate runs
            db.execute(
                "SELECT last_run FROM task_runs "
                "WHERE task_name = 'execute_trade_agreements'"
            )
            row = db.fetchone()
            if row and row[0]:
                import datetime

                now = datetime.datetime.now(datetime.timezone.utc)
                threshold = TASK_RUN_THRESHOLDS.get("execute_trade_agreements", 65)
                if (now - row[0]).total_seconds() < threshold:
                    print(f"trade_agreements: last run recent ({threshold}s), skipping")
                    return

            # Find all active agreements where next_execution is due
            db.execute(
                """
                SELECT id FROM trade_agreements
                WHERE status = 'active'
                  AND next_execution IS NOT NULL
                  AND next_execution <= now()
                ORDER BY next_execution
                LIMIT 100
            """
            )

            due_agreements = db.fetchall()

            if not due_agreements:
                # Update last run even if nothing to do
                db.execute(
                    """
                    INSERT INTO task_runs (task_name, last_run)
                    VALUES ('execute_trade_agreements', now())
                    ON CONFLICT (task_name) DO UPDATE SET last_run = now()
                """
                )
                conn.commit()
                return

            executed = 0
            failed = 0

            for (agreement_id,) in due_agreements:
                try:
                    success, msg = execute_trade_agreement(agreement_id)
                    if success:
                        executed += 1
                    else:
                        failed += 1
                        print(
                            f"trade_agreements: agreement {agreement_id} "
                            f"failed: {msg}"
                        )
                except Exception as e:
                    failed += 1
                    print(f"trade_agreements: agreement {agreement_id} error: {e}")
                    traceback.print_exc()

            # Update last run time
            db.execute(
                """
                INSERT INTO task_runs (task_name, last_run)
                VALUES ('execute_trade_agreements', now())
                ON CONFLICT (task_name) DO UPDATE SET last_run = now()
            """
            )
            conn.commit()

            elapsed_time = time.perf_counter() - start_time
            print(
                f"trade_agreements: executed={executed}, failed={failed} "
                f"in {elapsed_time:.2f}s"
            )

        except Exception as e:
            print(f"execute_trade_agreements: error - {e}")
            traceback.print_exc()
        finally:
            db.execute("SELECT pg_advisory_unlock(9004)")
            conn.commit()


def _create_game_tick_log(db):
    """Create and return a tick log row for the current global tick run."""
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS game_tick_logs (
            tick_id BIGSERIAL PRIMARY KEY,
            tick_type VARCHAR(40) NOT NULL DEFAULT 'global_tick',
            status VARCHAR(20) NOT NULL DEFAULT 'running',
            started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            finished_at TIMESTAMP WITH TIME ZONE,
            users_processed INTEGER NOT NULL DEFAULT 0,
            production_entries INTEGER NOT NULL DEFAULT 0,
            consumption_entries INTEGER NOT NULL DEFAULT 0,
            total_production BIGINT NOT NULL DEFAULT 0,
            total_consumption BIGINT NOT NULL DEFAULT 0,
            total_deserted_units BIGINT NOT NULL DEFAULT 0,
            error_message TEXT
        )
        """
    )
    db.execute(
        "INSERT INTO game_tick_logs (tick_type, status) "
        "VALUES ('global_tick', 'running') "
        "RETURNING tick_id"
    )
    return db.fetchone()[0]


def _finalize_game_tick_log(
    db,
    tick_id,
    *,
    status,
    users_processed=0,
    production_entries=0,
    consumption_entries=0,
    total_production=0,
    total_consumption=0,
    total_deserted_units=0,
    production_phase_ms=None,
    consumption_phase_ms=None,
    validation_phase_ms=None,
    total_duration_ms=None,
    error_message=None,
):
    """Finalize a game tick log row with outcomes and phase timings."""
    db.execute(
        """
        UPDATE game_tick_logs
        SET status=%s,
            finished_at=now(),
            users_processed=%s,
            production_entries=%s,
            consumption_entries=%s,
            total_production=%s,
            total_consumption=%s,
            total_deserted_units=%s,
            error_message=%s
        WHERE tick_id=%s
        """,
        (
            status,
            users_processed,
            production_entries,
            consumption_entries,
            total_production,
            total_consumption,
            total_deserted_units,
            error_message,
            tick_id,
        ),
    )


def global_tick():
    """Run the normalized global game tick with phase timing.

    Phases:
    1) Production from user_buildings + building_dictionary effect values
    2) Military maintenance consumption from user_military + unit_dictionary.
       Resources bottom out at 0 — units are never deleted.
       Units whose maintenance resource is depleted become unusable in combat
       (attack/defense power → 0) until the player resupplies.
    3) Log the tick execution in game_tick_logs with phase timings

    If any phase exceeds 30 seconds, a warning is logged.
    """
    from database import get_db_connection
    from psycopg2.extras import execute_batch, RealDictCursor

    with get_db_connection() as conn:
        if not try_pg_advisory_lock(conn, 9010, "global_tick"):
            return

        db = conn.cursor()
        dbdict = conn.cursor(cursor_factory=RealDictCursor)

        tick_id = None
        tick_start = time.time()
        users_processed = set()
        production_entries = 0
        consumption_entries = 0
        total_production = 0
        total_consumption = 0
        production_phase_ms = 0
        consumption_phase_ms = 0

        try:
            # Ensure we do not double-run in short windows.
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS task_runs (
                    task_name TEXT PRIMARY KEY,
                    last_run TIMESTAMP WITH TIME ZONE
                )
                """
            )
            db.execute(
                "INSERT INTO task_runs (task_name, last_run) VALUES (%s, NULL) "
                "ON CONFLICT DO NOTHING",
                ("global_tick",),
            )
            db.execute(
                "SELECT last_run FROM task_runs WHERE task_name=%s FOR UPDATE",
                ("global_tick",),
            )
            row = db.fetchone()
            if should_skip_task(row, "global_tick"):
                return

            db.execute(
                "UPDATE task_runs SET last_run = now() WHERE task_name = %s",
                ("global_tick",),
            )

            tick_id = _create_game_tick_log(db)

            # -----------------------------------------------------------------
            # Production phase
            # -----------------------------------------------------------------
            production_start = time.time()
            resource_names = set(BUILDING_PRODUCTION_RESOURCE_MAP.values())

            dbdict.execute(
                "SELECT resource_id, name "
                "FROM resource_dictionary "
                "WHERE name = ANY(%s)",
                (list(resource_names),),
            )
            resource_id_by_name = {
                row["name"]: row["resource_id"] for row in dbdict.fetchall()
            }

            building_id_to_resource_id = {}
            for bname, rname in BUILDING_PRODUCTION_RESOURCE_MAP.items():
                rid = resource_id_by_name.get(rname)
                if rid is not None:
                    building_id_to_resource_id[bname] = rid

            if building_id_to_resource_id:
                bnames = list(building_id_to_resource_id.keys())
                dbdict.execute(
                    """
                    SELECT
                        ub.user_id,
                        bd.name AS building_name,
                        SUM((ub.quantity::numeric * bd.effect_value))::bigint
                            AS produced_amount
                    FROM user_buildings ub
                    JOIN building_dictionary bd ON bd.building_id = ub.building_id
                    WHERE ub.quantity > 0
                      AND bd.effect_type = 'resource_production'
                      AND bd.name = ANY(%s)
                    GROUP BY ub.user_id, bd.name
                    """,
                    (bnames,),
                )
                prod_rows = dbdict.fetchall()
            else:
                prod_rows = []

            prod_updates = []
            for row in prod_rows:
                user_id = row["user_id"]
                building_name = row["building_name"]
                produced_amount = int(row["produced_amount"] or 0)
                resource_id = building_id_to_resource_id.get(building_name)
                if produced_amount <= 0 or resource_id is None:
                    continue
                prod_updates.append((user_id, resource_id, produced_amount))
                users_processed.add(user_id)
                production_entries += 1
                total_production += produced_amount

            if prod_updates:
                execute_batch(
                    db,
                    """
                    INSERT INTO user_economy
                        (user_id, resource_id, quantity, updated_at)
                    VALUES (%s, %s, %s, now())
                    ON CONFLICT (user_id, resource_id)
                    DO UPDATE SET
                        quantity = user_economy.quantity + EXCLUDED.quantity,
                        updated_at = now()
                    """,
                    prod_updates,
                    page_size=500,
                )

            production_phase_ms = int((time.time() - production_start) * 1000)
            if production_phase_ms > 30000:
                logger.warning(
                    f"Production phase exceeded 30s: {production_phase_ms}ms, "
                    f"prod_entries={production_entries}"
                )

            # -----------------------------------------------------------------
            # Consumption phase
            # -----------------------------------------------------------------
            consumption_start = time.time()
            dbdict.execute(
                """
                SELECT
                    um.user_id,
                    ud.maintenance_cost_resource_id AS resource_id,
                    SUM((um.quantity::numeric * ud.maintenance_cost_amount))::bigint
                        AS required_amount
                FROM user_military um
                JOIN unit_dictionary ud ON ud.unit_id = um.unit_id
                WHERE um.quantity > 0
                  AND ud.maintenance_cost_resource_id IS NOT NULL
                  AND ud.maintenance_cost_amount > 0
                GROUP BY um.user_id, ud.maintenance_cost_resource_id
                """
            )
            cost_rows = dbdict.fetchall()

            if cost_rows:
                impacted_users = sorted({row["user_id"] for row in cost_rows})
                impacted_resources = sorted({row["resource_id"] for row in cost_rows})

                dbdict.execute(
                    """
                    SELECT user_id, resource_id, quantity
                    FROM user_economy
                    WHERE user_id = ANY(%s)
                      AND resource_id = ANY(%s)
                    """,
                    (impacted_users, impacted_resources),
                )
                balance_map = {
                    (row["user_id"], row["resource_id"]): int(row["quantity"] or 0)
                    for row in dbdict.fetchall()
                }

                deductions = []
                deficits = {}
                for row in cost_rows:
                    user_id = row["user_id"]
                    resource_id = row["resource_id"]
                    required_amount = int(row["required_amount"] or 0)
                    if required_amount <= 0:
                        continue

                    available = balance_map.get((user_id, resource_id), 0)
                    deducted = (
                        required_amount if available >= required_amount else available
                    )
                    deficit = required_amount - deducted

                    if deducted > 0:
                        deductions.append((deducted, user_id, resource_id))
                        users_processed.add(user_id)
                        consumption_entries += 1
                        total_consumption += deducted
                        balance_map[(user_id, resource_id)] = max(
                            available - deducted, 0
                        )

                    if deficit > 0:
                        deficits[(user_id, resource_id)] = {
                            "required": required_amount,
                            "available": available,
                            "deficit": deficit,
                        }

                if deductions:
                    execute_batch(
                        db,
                        """
                        UPDATE user_economy
                        SET quantity = GREATEST(quantity - %s, 0),
                            updated_at = now()
                        WHERE user_id = %s AND resource_id = %s
                        """,
                        deductions,
                        page_size=500,
                    )

                consumption_phase_ms = int((time.time() - consumption_start) * 1000)
                if consumption_phase_ms > 30000:
                    logger.warning(
                        f"Consumption phase exceeded 30s: {consumption_phase_ms}ms, "
                        f"cons_entries={consumption_entries}"
                    )

            # Disbandment/desertion removed: units are never deleted due to
            # resource deficits. Instead, units whose maintenance resource is
            # at 0 are treated as 'unusable' in combat (attack/defense → 0)
            # via Units.unusable_units in units.py. Resources bottom out at 0.

            total_duration_ms = int((time.time() - tick_start) * 1000)
            if total_duration_ms > 30000:
                logger.warning(f"Global tick exceeded 30s total: {total_duration_ms}ms")

            _finalize_game_tick_log(
                db,
                tick_id,
                status="completed",
                users_processed=len(users_processed),
                production_entries=production_entries,
                consumption_entries=consumption_entries,
                total_production=total_production,
                total_consumption=total_consumption,
                total_deserted_units=0,
            )
            conn.commit()

            print(
                "global_tick: completed "
                f"users={len(users_processed)} "
                f"prod_entries={production_entries} cons_entries={consumption_entries} "
                f"produced={total_production} consumed={total_consumption} "
                f"total_ms={total_duration_ms}"
            )

        except Exception as e:
            err = str(e)
            total_duration_ms = int((time.time() - tick_start) * 1000)
            try:
                if tick_id is not None:
                    _finalize_game_tick_log(
                        db,
                        tick_id,
                        status="failed",
                        users_processed=len(users_processed),
                        production_entries=production_entries,
                        consumption_entries=consumption_entries,
                        total_production=total_production,
                        total_consumption=total_consumption,
                        total_deserted_units=0,
                        error_message=err,
                    )
                conn.commit()
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
            handle_exception(e)
            raise
        finally:
            try:
                release_pg_advisory_lock(conn, 9010)
            except Exception:
                pass


@celery.task()
def task_execute_trade_agreements():
    """Celery task to execute due trade agreements."""
    _run_with_deadlock_retries(execute_due_trade_agreements, "execute_trade_agreements")


@celery.task()
@leader_only(ttl_seconds=540)
def task_global_tick():
    """Celery task for normalized global production/consumption tick."""
    _run_with_deadlock_retries(global_tick, "global_tick")

    # Safety net: if hourly province revenue stalls, kick it from global tick.
    # This avoids long "resources frozen" windows when beat scheduling misses.
    try:
        stale_seconds = int(os.getenv("PROV_REV_STALE_SECONDS", "5400"))
        if is_task_stale("generate_province_revenue", stale_seconds):
            print(
                "global_tick watchdog: generate_province_revenue appears stale; "
                "triggering recovery run"
            )
            _run_with_deadlock_retries(
                generate_province_revenue,
                "generate_province_revenue_watchdog",
            )
    except Exception as e:
        print(f"global_tick watchdog failed: {e}")

    # Safety net: if population growth stalls, recover it from global tick too.
    # Keeps food/population mechanics from appearing "frozen" between scheduler gaps.
    try:
        stale_seconds = int(os.getenv("POP_GROWTH_STALE_SECONDS", "5400"))
        if is_task_stale("population_growth", stale_seconds):
            print(
                "global_tick watchdog: population_growth appears stale; "
                "triggering recovery run"
            )
            _run_with_deadlock_retries(
                population_growth,
                "population_growth_watchdog",
            )
    except Exception as e:
        print(f"global_tick population watchdog failed: {e}")

    # Safety net: recover tax income loop if it stalls.
    try:
        stale_seconds = int(os.getenv("TAX_INCOME_STALE_SECONDS", "5400"))
        if is_task_stale("tax_income", stale_seconds):
            print(
                "global_tick watchdog: tax_income appears stale; "
                "triggering recovery run"
            )
            _run_with_deadlock_retries(
                tax_income,
                "tax_income_watchdog",
            )
    except Exception as e:
        print(f"global_tick tax watchdog failed: {e}")


# ---------------------------------------------------------------------------
# Economy snapshot task
# ---------------------------------------------------------------------------


@celery.task(name="tasks.task_economy_snapshot")
def task_economy_snapshot():
    """Periodic snapshot of total resources in the game economy."""
    try:
        from admin_tools import take_economy_snapshot

        take_economy_snapshot()
        print("economy_snapshot: completed successfully")
    except Exception as e:
        print(f"economy_snapshot: failed — {e}")
