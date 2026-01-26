from celery import Celery
import psycopg2
import os
import time
from dotenv import load_dotenv
from attack_scripts import Economy
import math

# Toggle noisy per-building revenue logs (default off in production)
VERBOSE_REVENUE_LOGS = os.getenv("VERBOSE_REVENUE_LOGS") == "1"
import variables
from psycopg2.extras import RealDictCursor
from celery.schedules import crontab
import math

load_dotenv()
import config  # Parse Railway environment variables

redis_url = config.get_redis_url()
celery = Celery("app", broker=redis_url)
celery.conf.update(
    broker_url=redis_url, result_backend=redis_url, CELERY_BROKER_URL=redis_url
)

celery_beat_schedule = {
    # Staggered to reduce concurrent writes and deadlocks
    "tax_income": {
        "task": "tasks.task_tax_income",
        "schedule": crontab(minute="0"),  # at minute 0 each hour
    },
    "generate_province_revenue": {
        "task": "tasks.task_generate_province_revenue",
        "schedule": crontab(minute="25"),  # at minute 25 each hour (increased from 10)
    },
    "population_growth": {
        "task": "tasks.task_population_growth",
        "schedule": crontab(minute="45"),  # at minute 45 each hour (increased from 20)
    },
    "war_reparation_tax": {
        "task": "tasks.task_war_reparation_tax",
        # Run every day at midnight (UTC)
        "schedule": crontab(minute="0", hour="0"),
    },
    "manpower_increase": {
        "task": "tasks.task_manpower_increase",
        "schedule": crontab(minute="5", hour="*/4"),  # Run every 4 hours, minute 5
    },
    "backfill_missing_resources": {
        "task": "tasks.task_backfill_missing_resources",
        # Run daily 01:15 UTC to repair missing rows quietly
        "schedule": crontab(minute="15", hour="1"),
    },
}

celery.conf.update(
    timezone="UTC",
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    beat_schedule=celery_beat_schedule,
)


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
    """Attempt a PostgreSQL advisory lock to prevent overlapping task runs."""
    try:
        cur = conn.cursor()
        cur.execute("SELECT pg_try_advisory_lock(%s)", (lock_id,))
        row = cur.fetchone()
        if not row:
            # In some test fakes, fetchone() may return None; allow tasks to proceed
            # while logging a warning so tests that use simple fakes don't exit early.
            print(f"{label}: advisory lock query returned no rows - proceeding anyway")
            return True
        acquired = row[0]
        if not acquired:
            print(f"{label}: another run is already in progress, skipping")
        return acquired
    except Exception as e:
        print(f"{label}: failed to acquire advisory lock: {e}")
        return False


def release_pg_advisory_lock(conn, lock_id: int):
    try:
        cur = conn.cursor()
        cur.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))
    except Exception:
        pass


# Returns how many rations a player needs
def rations_needed(cId):
    from database import get_db_cursor

    with get_db_cursor() as db:
        # Use aggregated query instead of loop
        db.execute(
            "SELECT COALESCE(SUM(population), 0) FROM provinces WHERE userId=%s", (cId,)
        )
        total_population = db.fetchone()[0]
        return total_population // variables.RATIONS_PER


# Returns energy production and consumption from a certain province
def energy_info(province_id):
    from database import get_db_cursor

    with get_db_cursor() as db:
        production = 0
        consumption = 0

        consumers = variables.ENERGY_CONSUMERS
        producers = variables.ENERGY_UNITS

        infra = variables.NEW_INFRA

        # Fetch all data in a single query
        all_fields = consumers + producers
        query = f"SELECT {', '.join(all_fields)} FROM proInfra WHERE id=%s"
        db.execute(query, (province_id,))
        result = db.fetchone()

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

        db.execute("SELECT rations FROM resources WHERE id=%s", (user_id,))
        current_rations = db.fetchone()[0]

    if needed_rations == 0:
        needed_rations = 1

    rcp = (current_rations / needed_rations) - 1  # Normalizes the score to 0.
    if rcp > 0:
        rcp = 0

    score = -1 + (rcp * variables.NO_FOOD_TAX_MULTIPLIER)

    return score


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
        db.execute("SELECT consumer_goods FROM resources WHERE id=%s", (user_id,))
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
                "SELECT population, land FROM provinces WHERE userId=%s", (user_id,)
            )
            provinces = db.fetchall()
        except Exception:
            provinces = []

        if not provinces:  # User doesn't have any provinces
            return False, False

        income = 0
        for population, land in provinces:  # Base and land calculation
            land_multiplier = (land - 1) * variables.DEFAULT_LAND_TAX_MULTIPLIER
            if land_multiplier > 1:
                land_multiplier = 1  # Cap 100%

            base_multiplier = variables.DEFAULT_TAX_INCOME
            if 1 in policies:  # 1 Policy (1)
                base_multiplier *= 1.01  # Citizens pay 1% more tax)
            if 6 in policies:  # 6 Policy (2)
                base_multiplier *= 0.98
            if 4 in policies:  # 4 Policy (2)
                base_multiplier *= 0.98

            multiplier = base_multiplier + (base_multiplier * land_multiplier)
            income += multiplier * population

        # Consumer goods
        total_population = sum(p for p, _ in provinces)
        removed_consumer_goods = 0
        max_cg = math.ceil(total_population / variables.CONSUMER_GOODS_PER)

        if consumer_goods != 0 and max_cg != 0:
            if max_cg <= consumer_goods:
                # Enough consumer goods to fully cover consumption
                removed_consumer_goods = max_cg
                income *= variables.CONSUMER_GOODS_TAX_MULTIPLIER
            else:
                # Not enough goods to fully cover consumption; apply partial multiplier
                multiplier = consumer_goods / max_cg
                income *= 1 + (0.5 * multiplier)
                removed_consumer_goods = consumer_goods

        # Return (income, removed_consumer_goods) where removed_consumer_goods is a positive count
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
            # Ensure we only run once in a short window (protects against multiple beat schedulers)
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS task_runs (
                    task_name TEXT PRIMARY KEY,
                    last_run TIMESTAMP WITH TIME ZONE
                )
            """
            )
            db.execute(
                "SELECT last_run FROM task_runs WHERE task_name=%s", ("tax_income",)
            )
            row = db.fetchone()
            import datetime

            now = datetime.datetime.now(datetime.timezone.utc)
            # Skip if last run was within the last 55 seconds
            if row and row[0] and (now - row[0]).total_seconds() < 55:
                print("tax_income: last run too recent, skipping")
                try:
                    release_pg_advisory_lock(conn, 9001)
                except Exception:
                    pass
                return

            db.execute(
                "INSERT INTO task_runs (task_name, last_run) VALUES (%s, now()) ON CONFLICT (task_name) DO UPDATE SET last_run = now()",
                ("tax_income",),
            )
            start = time.time()
            dbdict = conn.cursor(cursor_factory=RealDictCursor)

            db.execute("SELECT id FROM users")
            users = db.fetchall()
            all_user_ids = [u[0] for u in users]

            if not all_user_ids:
                return

            # Bulk load all data upfront to eliminate N+1 queries
            # Load all stats (gold)
            stats_map = {}
            dbdict.execute(
                "SELECT id, gold FROM stats WHERE id = ANY(%s)", (all_user_ids,)
            )
            for row in dbdict.fetchall():
                # Support both RealDictCursor (dict rows) and simple tuple rows returned by test fakes
                if isinstance(row, dict):
                    stats_map[
                        row.get("id") or row.get("Id") or row.get("ID")
                    ] = row.get("gold")
                else:
                    stats_map[row[0]] = row[1]

            # Load all consumer_goods
            cg_map = {}
            dbdict.execute(
                "SELECT id, consumer_goods FROM resources WHERE id = ANY(%s)",
                (all_user_ids,),
            )
            for row in dbdict.fetchall():
                if isinstance(row, dict):
                    cg_map[row.get("id") or row.get("Id") or row.get("ID")] = (
                        row.get("consumer_goods") or 0
                    )
                else:
                    cg_map[row[0]] = row[1]

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
                    policies_map[row[0]] = row[1] if row[1] else []

            # Load all provinces (population, land) grouped by user
            provinces_map = {}  # user_id -> [(population, land), ...]
            dbdict.execute(
                "SELECT userId, population, land FROM provinces WHERE userId = ANY(%s)",
                (all_user_ids,),
            )
            for row in dbdict.fetchall():
                if isinstance(row, dict):
                    uid = row.get("userid") or row.get("userId") or row.get("user_id")
                    if uid not in provinces_map:
                        provinces_map[uid] = []
                    provinces_map[uid].append(
                        (row.get("population") or 0, row.get("land") or 0)
                    )
                else:
                    uid = row[0]
                    if uid not in provinces_map:
                        provinces_map[uid] = []
                    provinces_map[uid].append((row[1], row[2]))

            # Prepare batch updates
            money_updates = []
            cg_updates = []

            for user_id in all_user_ids:
                current_money = stats_map.get(user_id)
                if current_money is None:
                    continue

                consumer_goods = cg_map.get(user_id, 0)
                policies = policies_map.get(user_id, [])
                provinces = provinces_map.get(user_id, [])

                if not provinces:  # User doesn't have any provinces
                    continue

                # Calculate tax income inline (previously in calc_ti)
                income = 0
                total_population = 0
                for population, land in provinces:
                    total_population = population  # Keep track of last population for consumer_goods calc
                    land_multiplier = (land - 1) * variables.DEFAULT_LAND_TAX_MULTIPLIER
                    if land_multiplier > 1:
                        land_multiplier = 1  # Cap 100%

                    base_multiplier = variables.DEFAULT_TAX_INCOME
                    if 1 in policies:  # 1 Policy (1)
                        base_multiplier *= 1.01  # Citizens pay 1% more tax)
                    if 6 in policies:  # 6 Policy (2)
                        base_multiplier *= 0.98
                    if 4 in policies:  # 4 Policy (2)
                        base_multiplier *= 0.98

                    multiplier = base_multiplier + (base_multiplier * land_multiplier)
                    income += multiplier * population

                # Consumer goods calculation (use total population across all provinces)
                total_population = sum(p for p, _ in provinces)
                removed_consumer_goods = 0
                max_cg = (
                    math.ceil(total_population / variables.CONSUMER_GOODS_PER)
                    if total_population > 0
                    else 0
                )

                if consumer_goods and max_cg:
                    if consumer_goods >= max_cg:
                        removed_consumer_goods = max_cg
                        income *= variables.CONSUMER_GOODS_TAX_MULTIPLIER
                    else:
                        cg_multiplier = consumer_goods / max_cg
                        income *= 1 + (0.5 * cg_multiplier)
                        removed_consumer_goods = consumer_goods

                money = math.floor(income)
                if not money:
                    continue

                print(
                    f"Updated money for user id: {user_id}. Set {current_money} money to {current_money + money} money. (+{money})"
                )

                money_updates.append((money, user_id))
                if new_consumer_goods != 0:
                    cg_updates.append((abs(new_consumer_goods), user_id))

            # Execute batch updates
            if money_updates:
                execute_batch(
                    db,
                    "UPDATE stats SET gold=gold+%s WHERE id=%s",
                    money_updates,
                    page_size=100,
                )
            if cg_updates:
                execute_batch(
                    db,
                    "UPDATE resources SET consumer_goods=consumer_goods-%s WHERE id=%s",
                    cg_updates,
                    page_size=100,
                )

            conn.commit()
            duration = time.time() - start
            print(
                f"tax_income: updated {len(money_updates)} users in {duration:.2f}s (cg updates: {len(cg_updates)})"
            )
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
        db.execute("SELECT population FROM provinces WHERE id=%s", (pId,))
        curPop = db.fetchone()[0]

        maxPop = variables.DEFAULT_MAX_POPULATION  # Base max population: 1 million

        try:
            db.execute("SELECT cityCount FROM provinces WHERE id=%s", (pId,))
            cities = db.fetchone()[0]
        except TypeError:
            cities = 0

        maxPop += (
            cities * variables.CITY_MAX_POPULATION_ADDITION
        )  # Each city adds 750,000 population

        try:
            db.execute("SELECT land FROM provinces WHERE id=%s", (pId,))
            land = db.fetchone()[0]
        except TypeError:
            land = 0

        maxPop += (
            land * variables.LAND_MAX_POPULATION_ADDITION
        )  # Each land slot adds 120,000 population

        try:
            db.execute("SELECT happiness FROM provinces WHERE id=%s", (pId,))
            happiness = int(db.fetchone()[0])
        except TypeError:
            happiness = 0

        try:
            db.execute("SELECT pollution FROM provinces WHERE id=%s", (pId,))
            pollution = db.fetchone()[0]
        except TypeError:
            pollution = 0

        try:
            db.execute("SELECT productivity FROM provinces WHERE id=%s", (pId,))
            productivity = db.fetchone()[0]
        except TypeError:
            productivity = 0

        # Calculate happiness impact on max population
        # At 50% happiness: neutral (0% impact)
        # At 100% happiness: +6% to max population
        # At 0% happiness: -6% to max population
        happiness_multiplier = (
            (happiness - 50) * variables.DEFAULT_HAPPINESS_GROWTH_MULTIPLIER / 50
        )

        # Calculate pollution impact on max population
        # At 50% pollution: neutral (0% impact)
        # At 100% pollution: -3% to max population
        # At 0% pollution: +3% to max population
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
        # Max 0.5% growth with perfect rations
        growth_rate = rations_needed_percent * 0.5

        # Calculates the new rations of the player
        new_rations = rations - rations_needed
        if new_rations < 0:
            new_rations = 0
        new_rations = int(new_rations)

        newPop = int(round((maxPop / 100) * growth_rate))  # Growth as percentage of max

        db.execute("SELECT userid FROM provinces WHERE id=%s", (pId,))
        owner = db.fetchone()[0]

        try:
            db.execute("SELECT education FROM policies WHERE user_id=%s", (owner,))
            policies = db.fetchone()[0]
        except (TypeError, AttributeError):
            policies = []

        if 5 in policies:
            newPop = int(round(newPop * 1.2))  # 20% boost from education policy

        fullPop = int(curPop + newPop)

        if fullPop < 0:
            fullPop = 0

        return new_rations, fullPop


# Optimized population growth to minimize per-province queries and log noise
def population_growth():  # Function for growing population
    from database import get_db_connection
    from psycopg2.extras import execute_batch, RealDictCursor

    with get_db_connection() as conn:
        db = conn.cursor()
        dbdict = conn.cursor(cursor_factory=RealDictCursor)

        # Preload all provinces with the fields needed for growth calculations
        dbdict.execute(
            """
            SELECT id, userId, population, cityCount, land, happiness, pollution, productivity
            FROM provinces
            ORDER BY userId ASC
            """
        )
        provinces = dbdict.fetchall()

        if not provinces:
            return

        user_ids = [row["userid"] for row in provinces]
        unique_user_ids = sorted(set(user_ids))

        # Ensure resources rows exist for every user once, not per province
        execute_batch(
            db,
            "INSERT INTO resources (id) VALUES (%s) ON CONFLICT (id) DO NOTHING",
            [(uid,) for uid in unique_user_ids],
        )

        # Preload rations and policies into dicts for O(1) lookups
        dbdict.execute(
            "SELECT id, rations FROM resources WHERE id = ANY(%s)", (unique_user_ids,)
        )
        ration_map = {row["id"]: row["rations"] for row in dbdict.fetchall()}

        dbdict.execute(
            "SELECT user_id, education FROM policies WHERE user_id = ANY(%s)",
            (unique_user_ids,),
        )
        policy_map = {row["user_id"]: row["education"] for row in dbdict.fetchall()}

        def calc_pg_cached(province_row):
            province_id = province_row["id"]
            user_id = province_row["userid"]
            curPop = province_row["population"] or 0
            cities = province_row["citycount"] or 0
            land = province_row["land"] or 0
            happiness = int(province_row.get("happiness") or 0)
            pollution = province_row.get("pollution") or 0
            productivity = province_row.get("productivity") or 0

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

            rations_needed = curPop // variables.RATIONS_PER
            if rations_needed < 1:
                rations_needed = 1

            current_rations = ration_map.get(user_id, 0) or 0
            rations_ratio = current_rations / rations_needed
            if rations_ratio > 1:
                rations_ratio = 1

            # Slower, controlled population growth (prevents snowballing)
            growth_rate = rations_ratio * 0.5

            new_rations = current_rations - rations_needed
            if new_rations < 0:
                new_rations = 0
            new_rations = int(new_rations)

            newPop = int(round((maxPop / 100) * growth_rate))

            policies = policy_map.get(user_id) or []
            if 5 in policies:
                newPop = int(round(newPop * 1.2))

            fullPop = int(curPop + newPop)
            if fullPop < 0:
                fullPop = 0

            return user_id, new_rations, fullPop

        rations_updates = []
        population_updates = []

        for province_row in provinces:
            try:
                user_id, rations, population = calc_pg_cached(province_row)
                rations_updates.append((rations, user_id))
                population_updates.append((population, province_row["id"]))
            except Exception as e:
                handle_exception(e)
                continue

        if rations_updates:
            execute_batch(
                db, "UPDATE resources SET rations=%s WHERE id=%s", rations_updates
            )
        if population_updates:
            execute_batch(
                db, "UPDATE provinces SET population=%s WHERE id=%s", population_updates
            )

        print(
            f"population_growth: updated {len(population_updates)} provinces across {len(unique_user_ids)} users"
        )


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


def generate_province_revenue():  # Runs each hour
    from database import get_db_connection
    from psycopg2.extras import RealDictCursor, execute_batch

    start_time = time.time()
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
            "SELECT last_run FROM task_runs WHERE task_name=%s",
            ("generate_province_revenue",),
        )
        row = db.fetchone()
        import datetime

        now = datetime.datetime.now(datetime.timezone.utc)
        # Skip if this task ran within the last 90 seconds (allow some leeway for long runs)
        if row and row[0] and (now - row[0]).total_seconds() < 90:
            print("generate_province_revenue: last run too recent, skipping")
            try:
                release_pg_advisory_lock(conn, 9002)
            except Exception:
                pass
            return

        db.execute(
            "INSERT INTO task_runs (task_name, last_run) VALUES (%s, now()) ON CONFLICT (task_name) DO UPDATE SET last_run = now()",
            ("generate_province_revenue",),
        )
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
            db.execute(
                "SELECT proInfra.id, provinces.userId, provinces.land, provinces.productivity FROM proInfra INNER JOIN provinces ON proInfra.id=provinces.id ORDER BY id ASC"
            )
            infra_ids = db.fetchall()
        except Exception:
            infra_ids = []

        # ============ BULK PRELOAD DATA TO ELIMINATE N+1 QUERIES ============
        # Get all unique user_ids and province_ids
        all_user_ids = list(set(row[1] for row in infra_ids))
        all_province_ids = [row[0] for row in infra_ids]

        # Preload all upgrades for all users at once (instead of per-loop queries)
        upgrades_map = {}
        if all_user_ids:
            dbdict.execute(
                "SELECT user_id, * FROM upgrades WHERE user_id = ANY(%s)",
                (all_user_ids,),
            )
            for row in dbdict.fetchall():
                upgrades_map[row["user_id"]] = dict(row)

        # Preload all policies for all users at once
        policies_map = {}
        if all_user_ids:
            dbdict.execute(
                "SELECT user_id, education FROM policies WHERE user_id = ANY(%s)",
                (all_user_ids,),
            )
            for row in dbdict.fetchall():
                policies_map[row["user_id"]] = row["education"]

        # Preload all proInfra data for all provinces at once
        proinfra_map = {}
        if all_province_ids:
            dbdict.execute(
                "SELECT * FROM proInfra WHERE id = ANY(%s)", (all_province_ids,)
            )
            for row in dbdict.fetchall():
                proinfra_map[row["id"]] = dict(row)

        # Preload all stats (gold) for all users at once
        stats_map = {}
        if all_user_ids:
            dbdict.execute(
                "SELECT id, gold FROM stats WHERE id = ANY(%s)", (all_user_ids,)
            )
            for row in dbdict.fetchall():
                stats_map[row["id"]] = row["gold"]

        # Preload all resources for all users at once
        resources_map = {}
        if all_user_ids:
            dbdict.execute(
                "SELECT * FROM resources WHERE id = ANY(%s)", (all_user_ids,)
            )
            for row in dbdict.fetchall():
                resources_map[row["id"]] = dict(row)

        # Ensure all users have resource rows (batch insert)
        if all_user_ids:
            execute_batch(
                db,
                "INSERT INTO resources (id) VALUES (%s) ON CONFLICT (id) DO NOTHING",
                [(uid,) for uid in all_user_ids],
            )

        # Track accumulated changes for batch updates at end
        gold_deductions = {}  # user_id -> total_deducted

        # Preload province data for effects tracking (happiness, productivity, pollution, consumer_spending, energy)
        provinces_data = (
            {}
        )  # province_id -> {happiness, productivity, pollution, consumer_spending, energy, ...}
        if all_province_ids:
            dbdict.execute(
                """
                SELECT id, happiness, productivity, pollution, consumer_spending,
                       energy, population
                FROM provinces WHERE id = ANY(%s)
            """,
                (all_province_ids,),
            )
            for row in dbdict.fetchall():
                prov_dict = dict(row)
                prov_dict[
                    "energy"
                ] = 0  # Reset energy to 0 (will be built up by nuclear_reactors)
                provinces_data[row["id"]] = prov_dict

        for province_id, user_id, land, productivity in infra_ids:
            # Initialize tracking for this user
            if user_id not in gold_deductions:
                gold_deductions[user_id] = 0

            # Use preloaded upgrades instead of per-loop query
            upgrades = upgrades_map.get(user_id, {})
            if not upgrades:
                dbdict.execute("SELECT * FROM upgrades WHERE user_id=%s", (user_id,))
                result = dbdict.fetchone()
                upgrades = dict(result) if result else {}
                upgrades_map[user_id] = upgrades

            # Use preloaded policies instead of per-loop query
            policies = policies_map.get(user_id, [])
            if policies is None:
                policies = []

            # Use preloaded proInfra instead of per-loop query
            units = proinfra_map.get(province_id, {})
            if not units:
                dbdict.execute("SELECT * FROM proInfra WHERE id=%s", (province_id,))
                result = dbdict.fetchone()
                units = dict(result) if result else {}
                proinfra_map[province_id] = units

            for unit in columns:
                unit_amount = units[unit]

                if unit_amount == 0:
                    continue

                unit_category = find_unit_category(unit)
                try:
                    effminus = infra[unit].get("effminus", {})
                    minus = infra[unit].get("minus", {})
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

                    if 1 in policies and unit == "universities":
                        operating_costs *= 1.14
                    if 3 in policies and unit == "universities":
                        operating_costs *= 1.18
                    if 6 in policies and unit == "universities":
                        operating_costs *= 0.93

                    ### CHEAPER MATERIALS
                    if unit_category == "industry" and upgrades.get("cheapermaterials"):
                        operating_costs *= 0.8
                    ### ONLINE SHOPPING
                    if unit == "malls" and upgrades.get("onlineshopping"):
                        operating_costs *= 0.7

                    # Use preloaded gold and track deductions (instead of per-building SELECT+UPDATE)
                    current_money = stats_map.get(user_id, 0) - gold_deductions.get(
                        user_id, 0
                    )

                    operating_costs = int(operating_costs)

                    # Boolean for whether a player has enough resources, energy, money to power his building
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

                    # Use tracked energy in provinces_data instead of per-building SELECT
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
                    if not resources:
                        dbdict.execute(
                            "SELECT * FROM resources WHERE id=%s", (user_id,)
                        )
                        result = dbdict.fetchone()
                        resources = dict(result) if result else {}
                        resources_map[user_id] = resources

                    for resource, amount in minus.items():
                        amount *= unit_amount
                        current_resource = resources.get(resource, 0)

                        ### AUTOMATION INTEGRATION
                        if unit == "component_factories" and upgrades.get(
                            "automationintegration"
                        ):
                            amount *= 0.75
                        ### LARGER FORGES
                        if unit == "steel_mills" and upgrades.get("largerforges"):
                            amount *= 0.7

                        new_resource = current_resource - amount

                        if new_resource < 0:
                            has_enough_stuff["status"] = False
                            has_enough_stuff["issues"].append(resource)
                            log_verbose(
                                f"F | USER: {user_id} | PROVINCE: {province_id} | {unit} ({unit_amount}) | Failed to minus {amount} of {resource} ({current_resource})"
                            )
                        else:
                            # Update local cache and track for batch update
                            resources_map[user_id][resource] = new_resource
                            log_verbose(
                                f"S | MINUS | USER: {user_id} | PROVINCE: {province_id} | {unit} ({unit_amount}) | {resource} {current_resource}={new_resource} (-{current_resource-new_resource})"
                            )

                    if not has_enough_stuff["status"]:
                        log_verbose(
                            f"F | USER: {user_id} | PROVINCE: {province_id} | {unit} ({unit_amount}) | Not enough {', '.join(has_enough_stuff['issues'])}"
                        )
                        continue

                    plus = infra[unit].get("plus", {})

                    ### BETTER ENGINEERING
                    if unit == "nuclear_reactors" and upgrades["betterengineering"]:
                        plus["energy"] += 6

                    eff = infra[unit].get("eff", {})

                    if unit == "universities" and 3 in policies:
                        eff["productivity"] *= 1.10
                        eff["happiness"] *= 1.10

                    if unit == "hospitals":
                        if upgrades["nationalhealthinstitution"]:
                            eff["happiness"] *= 1.3
                            eff["happiness"] = int(eff["happiness"])

                    if unit == "monorails":
                        if upgrades["highspeedrail"]:
                            eff["productivity"] *= 1.2
                            eff["productivity"] = int(eff["productivity"])

                    """
                    print(f"Unit: {unit}")
                    print(f"Add {plus_amount} to {plus_resource}")
                    print(f"Remove ${operating_costs} as operating costs")
                    print(f"\n")
                    """
                    if unit == "bauxite_mines" and upgrades["strongerexplosives"]:
                        # TODO: fix this plus_amount variable
                        plus_amount_multiplier += 0.45

                    if unit == "farms":
                        if upgrades["advancedmachinery"]:
                            plus_amount_multiplier += 0.5

                        plus_amount += int(
                            land * variables.LAND_FARM_PRODUCTION_ADDITION
                        )

                    # Function for _plus
                    for resource, amount in plus.items():
                        amount += plus_amount
                        amount *= unit_amount
                        amount *= plus_amount_multiplier
                        # Normalize production to integer units so we don't persist fractional
                        # resources (e.g., 0.5 rations). Use ceil to avoid losing tiny outputs.
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
                            log_verbose(
                                f"S | PLUS |USER: {user_id} | PROVINCE: {province_id} | {unit} ({unit_amount}) | ADDING | {resource} | {amount}"
                            )

                        elif resource in user_resources:
                            # Update resources_map cache for batch write later
                            current_val = resources_map.get(user_id, {}).get(
                                resource, 0
                            )
                            resources_map[user_id][resource] = current_val + amount
                            log_verbose(
                                f"S | PLUS | USER: {user_id} | PROVINCE: {province_id} | {unit} ({unit_amount}) | ADDING | {resource} | {amount}"
                            )

                    # Function for completing an effect (adding pollution, etc)
                    def do_effect(eff, eff_amount, sign):
                        # Use preloaded province data instead of per-building SELECT
                        prov_data = provinces_data.get(province_id, {})
                        current_effect = prov_data.get(eff, 0)

                        ### GOVERNMENT REGULATION
                        if (
                            unit_category == "retail"
                            and upgrades.get("governmentregulation")
                            and eff == "pollution"
                            and sign == "+"
                        ):
                            eff_amount *= 0.75
                        ###
                        if unit == "universities" and 3 in policies:
                            eff_amount *= 1.1

                        eff_amount = math.ceil(
                            eff_amount
                        )  # Using math.ceil so universities +18% would work

                        if sign == "+":
                            new_effect = current_effect + eff_amount
                        elif sign == "-":
                            new_effect = current_effect - eff_amount

                        if eff in percentage_based:
                            if new_effect > 100:
                                new_effect = 100
                            if new_effect < 0:
                                new_effect = 0
                        else:
                            if new_effect < 0:
                                new_effect = 0

                        # Update local cache for batch write later
                        if province_id in provinces_data:
                            provinces_data[province_id][eff] = new_effect

                    for effect, amount in eff.items():
                        amount *= unit_amount
                        do_effect(effect, amount, "+")

                    for effect, amount in effminus.items():
                        amount *= unit_amount
                        do_effect(effect, amount, "-")

                    if 5 in policies:
                        # Update local cache instead of per-building UPDATE
                        prov_data = provinces_data.get(province_id, {})
                        current_prod = prov_data.get("productivity", 50)
                        new_prod = max(0, min(100, round(current_prod * 0.91)))
                        if province_id in provinces_data:
                            provinces_data[province_id]["productivity"] = new_prod
                    if 4 in policies:
                        # Update local cache instead of per-building UPDATE
                        prov_data = provinces_data.get(province_id, {})
                        current_prod = prov_data.get("productivity", 50)
                        new_prod = max(0, min(100, round(current_prod * 1.05)))
                        if province_id in provinces_data:
                            provinces_data[province_id]["productivity"] = new_prod
                    if 2 in policies:
                        # Update local cache instead of per-building UPDATE
                        prov_data = provinces_data.get(province_id, {})
                        current_hap = prov_data.get("happiness", 50)
                        new_hap = round(current_hap * 0.89)
                        if province_id in provinces_data:
                            provinces_data[province_id]["happiness"] = new_hap

                except Exception as e:
                    conn.rollback()
                    handle_exception(e)
                    continue

            processed += 1

        # ============ BATCH WRITE ALL ACCUMULATED CHANGES ============
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
        except Exception as e:
            conn.rollback()
            handle_exception(e)

        # Write all province changes in batch (happiness, productivity, pollution, consumer_spending, energy, rations)
        try:
            if provinces_data:
                province_updates = []
                for pid, data in provinces_data.items():
                    province_updates.append(
                        (
                            min(100, max(0, data.get("happiness", 50))),
                            min(100, max(0, data.get("productivity", 50))),
                            min(100, max(0, data.get("pollution", 0))),
                            min(100, max(0, data.get("consumer_spending", 50))),
                            data.get("energy", 0),
                            pid,
                        )
                    )
                if province_updates:
                    execute_batch(
                        db,
                        """
                        UPDATE provinces SET
                            happiness = %s,
                            productivity = %s,
                            pollution = %s,
                            consumer_spending = %s,
                            energy = %s
                        WHERE id = %s
                    """,
                        province_updates,
                        page_size=100,
                    )
                    log_verbose(f"Batch updated {len(province_updates)} provinces")
        except Exception as e:
            conn.rollback()
            handle_exception(e)

        # Write all resource changes in batch
        try:
            if resources_map:
                # Get list of resource columns we need to update
                resource_columns = [
                    "iron",
                    "steel",
                    "oil",
                    "lead",
                    "bauxite",
                    "gasoline",
                    "aluminum",
                    "rations",
                    "munitions",
                    "components",
                    "consumer_goods",
                ]
                for user_id, res_data in resources_map.items():
                    # Build dynamic update for each user with their resource values
                    set_clauses = []
                    values = []
                    for col in resource_columns:
                        if col in res_data:
                            set_clauses.append(f"{col} = %s")
                            values.append(
                                max(0, res_data[col])
                            )  # Ensure no negative values
                    if set_clauses and values:
                        values.append(user_id)
                        db.execute(
                            f"UPDATE resources SET {', '.join(set_clauses)} WHERE id = %s",
                            values,
                        )
                log_verbose(f"Batch updated resources for {len(resources_map)} users")
        except Exception as e:
            conn.rollback()
            handle_exception(e)

        # Final commit
        try:
            conn.commit()
        except Exception as e:
            conn.rollback()
            handle_exception(e)

        duration = time.time() - start_time
        print(
            f"generate_province_revenue: processed {processed} provinces in {duration:.2f}s (skipped={skipped_for_lock})"
        )

        try:
            release_pg_advisory_lock(conn, 9002)
        except Exception:
            pass


def war_reparation_tax():
    from database import get_db_cursor

    with get_db_cursor() as db:
        db.execute(
            "SELECT id,peace_date,attacker,attacker_morale,defender,defender_morale FROM wars WHERE (peace_date IS NOT NULL) AND (peace_offer_id IS NULL)"
        )
        truces = db.fetchall()

        for state in truces:
            war_id, peace_date, attacker, a_morale, defender, d_morale = state

            # For now we simply delete war record if no longer needed for reparation tax (NOTE: if we want history table for wars then move these peace redords to other table or reuse not needed wars table column -- marter )
            # If peace is made longer than a week (604800 = one week in seconds)
            if peace_date < (time.time() - 604800):
                db.execute("DELETE FROM wars WHERE id=%s", (war_id,))

            # Transfer resources to attacker (winner)
            else:
                if d_morale <= 0:
                    winner = attacker
                    loser = defender
                else:
                    winner = defender
                    loser = attacker

                eco = Economy(loser)

                # OPTIMIZATION: Fetch all resources and war_type in ONE query each instead of 30 queries
                resource_cols = ", ".join(Economy.resources)
                db.execute(
                    f"SELECT {resource_cols} FROM resources WHERE id=%s", (loser,)
                )
                resource_row = db.fetchone()
                resource_amounts = (
                    dict(zip(Economy.resources, resource_row)) if resource_row else {}
                )

                db.execute("SELECT war_type FROM wars WHERE id=%s", (war_id,))
                war_type = db.fetchone()

                for idx, resource in enumerate(Economy.resources):
                    resource_amount = resource_amounts.get(resource, 0) or 0

                    # This condition lower or doesn't give reparation_tax at all
                    # NOTE: for now it lowers to only 5% (the basic is 20%)
                    if war_type == "Raze":
                        eco.transfer_resources(
                            resource, resource_amount * (1 / 20), winner
                        )
                    else:
                        # transfer 20% of all resource (TODO: implement if and alliance won how to give it)
                        eco.transfer_resources(
                            resource, resource_amount * (1 / 5), winner
                        )


def _run_with_deadlock_retries(fn, label: str, max_retries: int = 3):
    """Run a DB-heavy function with retries on Postgres deadlocks and transient errors."""
    import random
    from psycopg2 import errors as pg_errors
    from psycopg2.errorcodes import DEADLOCK_DETECTED

    attempt = 0
    while True:
        try:
            return fn()
        except pg_errors.DeadlockDetected as e:
            attempt += 1
            if attempt > max_retries:
                print(
                    f"{label}: exceeded deadlock retries ({max_retries}). Last error: {e}"
                )
                raise
            backoff = 0.2 * attempt + random.uniform(0, 0.2)
            print(
                f"{label}: deadlock detected, retrying in {backoff:.2f}s (attempt {attempt}/{max_retries})"
            )
            try:
                time.sleep(backoff)
            except Exception:
                pass
            continue
        except psycopg2.InterfaceError as e:
            # Connection was closed (likely due to forked workers sharing pool). Attempt pool reset then retry once per attempt.
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
                    f"{label}: exceeded interface error retries ({max_retries}). Last error: {e}"
                )
                raise
            try:
                time.sleep(0.1 * attempt)
            except Exception:
                pass
            continue


@celery.task()
def task_population_growth():
    _run_with_deadlock_retries(population_growth, "population_growth")


@celery.task()
def task_tax_income():
    tax_income()


@celery.task()
def task_generate_province_revenue():
    _run_with_deadlock_retries(generate_province_revenue, "generate_province_revenue")


# Runs once a day
# Transfer X% of all resources (could depends on conditions like Raze war_type) to the winner side after a war


@celery.task()
def task_war_reparation_tax():
    war_reparation_tax()


@celery.task()
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

        # Bulk load current manpower
        manpower_map = {}
        dbdict.execute(
            "SELECT id, manpower FROM military WHERE id = ANY(%s)", (user_ids,)
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
                "UPDATE military SET manpower=manpower+%s WHERE id=%s",
                manpower_updates,
                page_size=100,
            )
        conn.commit()


def backfill_missing_resources():
    from database import get_db_connection
    from psycopg2.extras import execute_batch

    with get_db_connection() as conn:
        db = conn.cursor()
        # Find users missing a resources row
        db.execute(
            """
            SELECT u.id
            FROM users u
            LEFT JOIN resources r ON r.id = u.id
            WHERE r.id IS NULL
            """
        )
        missing = [row[0] for row in db.fetchall()]
        if not missing:
            return

        cols = ["id"] + variables.RESOURCES
        placeholders = ",".join(["%s"] * len(cols))
        sql = f"INSERT INTO resources ({','.join(cols)}) VALUES ({placeholders}) ON CONFLICT (id) DO NOTHING"

        params = []
        zeros = [0] * len(variables.RESOURCES)
        for user_id in missing:
            params.append([user_id] + zeros)

        try:
            execute_batch(db, sql, params)
            print(f"Backfilled resources for {len(missing)} users")
        except Exception as e:
            handle_exception(e)


@celery.task()
def task_backfill_missing_resources():
    _run_with_deadlock_retries(backfill_missing_resources, "backfill_missing_resources")
