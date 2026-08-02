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
from app_core.game_ticks.common import should_skip_task, handle_exception, log_verbose
from app_core.game_ticks.locks import try_pg_advisory_lock, release_pg_advisory_lock
from app_core.game_ticks.food import rations_needed



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

        # Slower, controlled population growth (prevents snowballing).
        # Squared so growth falls off steeply once distribution capacity
        # can't keep up with population, not just linearly (Discord report:
        # nation fed for 9.5M but at 15M pop still "grows enormously
        # quickly" — a 63%-fed nation was only losing 37% of its growth
        # rate under the old linear scaling).
        base_growth_rate = (rations_needed_percent**2) * 0.15

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

        dbdict = conn.cursor(cursor_factory=RealDictCursor)

        CHUNK_SIZE = 200

        # Preload province IDs only (lightweight) to chunk the work
        dbdict.execute(
            """
             SELECT p.id, p.userId, p.population, p.citycount, p.land,
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

        user_total_provinces = {}
        user_total_land = {}
        for prov in all_provinces:
            uid = prov["userid"]
            user_total_provinces[uid] = user_total_provinces.get(uid, 0) + 1
            user_total_land[uid] = user_total_land.get(uid, 0) + (prov["land"] or 0)

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
                      'distribution_centers', 'food_banks', 'gas_stations',
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

            # Squared: see calc_pg() above for the reasoning (player-reported
            # over-fast growth while significantly under distribution capacity).
            base_growth_rate = (rations_ratio**2) * 0.15

            pop_ratio = curPop / maxPop if maxPop > 0 else 1
            diminishing_factor = max(0.05, 1 - (pop_ratio**2))
            growth_rate = base_growth_rate * diminishing_factor

            newPop = int(round((maxPop / 100) * growth_rate))

            starvation_deaths = 0
            grace_period = (user_total_provinces.get(user_id, 1) <= 1) and (user_total_land.get(user_id, 1) <= 20)
            if rations_ratio < 1.0 and not grace_period:
                # Up to 1% of the current population dies per hour at 0 rations
                starvation_rate = (1.0 - rations_ratio) * 0.01
                starvation_deaths = int(round(curPop * starvation_rate))

            fullPop = int(curPop + newPop - starvation_deaths)
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
            db.execute(
                "UPDATE task_runs SET last_run = now() WHERE task_name = %s",
                ("population_growth",),
            )
            conn.commit()
        except Exception as e:
            handle_exception(e, "population_growth")

        try:
            release_pg_advisory_lock(conn, 9003)
        except Exception:
            pass




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

            # Self-heal: a province with working population but zero recorded
            # education is corrupt state (workers must belong to an education
            # tier, or jobs_available=0 floors every building at 20% efficiency —
            # e.g. power plants underproduce and can't run factories). This
            # happened to a couple of provinces whose starting workforce was
            # never counted into edu_none. Treat unaccounted workers as base
            # (uneducated) so they can be employed. Idempotent: only fires when
            # education is fully zero.
            if (pop_working or 0) > 0:
                db.execute(
                    """
                    UPDATE provinces
                    SET edu_none = pop_working
                    WHERE id = %s
                      AND COALESCE(edu_none,0)+COALESCE(edu_highschool,0)
                          +COALESCE(edu_college,0) = 0
                      AND pop_working > 0
                    """,
                    (province_id,),
                )

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
                SELECT bd.name, COALESCE(SUM(ub.quantity), 0)
                FROM user_buildings ub
                JOIN building_dictionary bd
                    ON bd.building_id = ub.building_id
                WHERE ub.province_id = %s
                    AND bd.name IN ('high_school', 'universities')
                GROUP BY bd.name
                """,
                (province_id,),
            )
            school_rows = {r[0]: int(r[1]) for r in db.fetchall()}
            hs_buildings = school_rows.get("high_school", 0)
            uni_buildings = school_rows.get("universities", 0)
            # Each school building can graduate 500 students per tick
            hs_capacity = hs_buildings * 500
            uni_capacity = uni_buildings * 500
            school_capacity = hs_capacity + uni_capacity

            # Apply Mandatory Schooling policy to graduation rate
            graduation_rate = variables.DEMO_AGING_RATES["children_to_working"]
            if variables.POLICY_MANDATORY_SCHOOLING in policies:
                graduation_rate *= variables.POLICY_SCHOOLING_GRADUATION_MULTIPLIER

            # Calculate how many children can graduate
            can_graduate = min(
                pop_children,
                int(round(pop_children * graduation_rate)),
            )
            graduates = min(can_graduate, school_capacity) if school_capacity > 0 else 0

            # Remaining children who age but don't graduate
            non_graduates = can_graduate - graduates

            # Distribute graduates: universities first, then high schools
            if graduates > 0:
                uni_grads = min(graduates, uni_capacity)
                hs_grads = min(graduates - uni_grads, hs_capacity)

                if uni_grads > 0:
                    db.execute(
                        "UPDATE provinces SET edu_college = "
                        "edu_college + %s WHERE id = %s",
                        (uni_grads, province_id),
                    )
                if hs_grads > 0:
                    db.execute(
                        "UPDATE provinces SET edu_highschool = "
                        "edu_highschool + %s WHERE id = %s",
                        (hs_grads, province_id),
                    )

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




def find_unit_category(unit):
    categories = variables.INFRA_TYPE_BUILDINGS
    for name, list in categories.items():
        if unit in list:
            return name
    return False


