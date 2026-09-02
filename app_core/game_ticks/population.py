from celery import Celery
import psycopg2
import os
import time
import datetime
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
                 COALESCE(p.pop_elderly, 0) AS pop_elderly,
                 COALESCE(p.legacy_max_population, 0) AS legacy_max_population
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
        # Tracked separately from dist_cap_map (which spans 6 building types,
        # some very cheap) so the rations-storage buffer below can't be
        # trivially inflated by mass-building the cheapest distribution
        # building -- it's tied specifically to distribution_centers.
        distribution_centers_map = {}
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
                if bname == "distribution_centers":
                    distribution_centers_map[uid] = qty

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
        # Spoilage grace period: see variables.RATIONS_SPOILAGE_GRACE_PERIOD_END.
        in_spoilage_grace_period = (
            datetime.datetime.now(datetime.timezone.utc)
            < variables.RATIONS_SPOILAGE_GRACE_PERIOD_END
        )
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
            user_effective_rations[uid] = distributable

            # Rations spoilage: a banked surplus above the buffer decays each
            # hour instead of being able to sustain unattended growth
            # indefinitely. Buffer = free baseline (days of this user's
            # current hourly need) + extra capacity from distribution_centers
            # they've built.
            spoilage = 0
            if not in_spoilage_grace_period:
                buffer = (
                    needed * 24 * variables.RATIONS_BASELINE_BUFFER_DAYS
                    + distribution_centers_map.get(uid, 0)
                    * variables.RATIONS_STORAGE_PER_DISTRIBUTION_CENTER
                )
                remaining_after_consumption = warehouse - actually_consumed
                if remaining_after_consumption > buffer:
                    excess = remaining_after_consumption - buffer
                    spoilage = int(round(excess * variables.RATIONS_EXCESS_DECAY_RATE))

            user_rations_to_deduct[uid] = actually_consumed + spoilage

        def calc_population_growth(province_row):
            """Calculate population growth for a single province."""
            user_id = province_row["userid"]
            curPop = province_row["population"] or 0
            cities = province_row["citycount"] or 0
            land = province_row["land"] or 0
            happiness = int(province_row.get("happiness") or 0)
            pollution = province_row.get("pollution") or 0
            legacy_max_population = province_row.get("legacy_max_population") or 0

            # Saturating curve (approaches a cap asymptotically) instead of the
            # old unbounded linear terms, so buying unlimited cities/land no
            # longer produces unbounded maxPop.
            city_contribution = variables.CITY_POP_CAP * (
                1 - math.exp(-cities / variables.CITY_POP_SOFTNESS)
            )
            land_contribution = variables.LAND_POP_CAP * (
                1 - math.exp(-land / variables.LAND_POP_SOFTNESS)
            )
            maxPop = variables.DEFAULT_MAX_POPULATION + city_contribution + land_contribution

            happiness_multiplier = (
                (happiness - 50) * variables.DEFAULT_HAPPINESS_GROWTH_MULTIPLIER / 50
            )
            pollution_multiplier = (
                (pollution - 50) * -variables.DEFAULT_POLLUTION_GROWTH_MULTIPLIER / 50
            )

            maxPop = int(maxPop * (1 + happiness_multiplier + pollution_multiplier))
            if maxPop < variables.DEFAULT_MAX_POPULATION:
                maxPop = variables.DEFAULT_MAX_POPULATION
            # Grandfather floor: population that already existed before this
            # curve shipped never gets retroactively shrunk -- it just stops
            # growing further until legitimate new land/city purchases push
            # the curve's result past this floor.
            if legacy_max_population > maxPop:
                maxPop = legacy_max_population

            total_needed = user_total_rations_needed.get(user_id, 1)
            effective_rations = user_effective_rations.get(user_id, 0) or 0
            rations_ratio = effective_rations / total_needed if total_needed > 0 else 0
            if rations_ratio > 1:
                rations_ratio = 1

            # Squared so growth falls off steeply once distribution capacity
            # can't keep up with population, not just linearly (player-reported
            # over-fast growth while significantly under distribution capacity).
            base_growth_rate = (rations_ratio**2) * 0.15

            pop_ratio = curPop / maxPop if maxPop > 0 else 1
            diminishing_factor = max(
                variables.POP_GROWTH_DIMINISHING_FLOOR, 1 - (pop_ratio**2)
            )
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


