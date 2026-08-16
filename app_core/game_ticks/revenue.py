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
from app_core.game_ticks.common import (
    should_skip_task,
    handle_exception,
    log_verbose,
    MAX_INT_32,
)
from app_core.game_ticks.locks import try_pg_advisory_lock, release_pg_advisory_lock
from app_core.game_ticks.population import find_unit_category



def generate_province_revenue():  # Runs each hour
    from database import get_db_connection, rollback_db_cursor
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

        # Do not commit last_run here — wait until resource/province writes
        # succeed so task_runs does not advance when economy rows are unchanged.
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

        max_chunks = int(os.getenv("PROVINCE_REVENUE_CHUNKS_PER_RUN", "50"))
        chunk_size = int(os.getenv("PROVINCE_REVENUE_CHUNK_SIZE", "500"))
        revenue_deadline = start_time + float(
            os.getenv("PROVINCE_REVENUE_TIME_BUDGET_SEC", "270")
        )
        chunks_completed = 0
        any_chunk_committed = False

        db.execute(
            "CREATE TABLE IF NOT EXISTS task_cursors ("
            "task_name TEXT PRIMARY KEY, last_id BIGINT)"
        )
        db.execute(
            "INSERT INTO task_cursors (task_name, last_id) "
            "VALUES (%s, %s) ON CONFLICT DO NOTHING",
            ("generate_province_revenue", 0),
        )

        while chunks_completed < max_chunks and time.perf_counter() < revenue_deadline:
            infra_ids = []
            try:
                db.execute(
                    "SELECT last_id FROM task_cursors WHERE task_name=%s",
                    ("generate_province_revenue",),
                )
                last_row = db.fetchone()
                last_proc = last_row[0] if last_row and last_row[0] is not None else 0
                db.execute(
                    "SELECT p.id, p.userId, p.land, p.productivity "
                    "FROM provinces p "
                    "WHERE p.id > %s ORDER BY p.id ASC LIMIT %s",
                    (last_proc, chunk_size),
                )
                infra_ids = db.fetchall()
                if not infra_ids:
                    # Cursor reached end — reset for next scheduled run and STOP.
                    # Do NOT re-fetch from the beginning; that would re-apply production
                    # multiple times within a single hourly tick.
                    db.execute(
                        "UPDATE task_cursors SET last_id=0 WHERE task_name=%s",
                        ("generate_province_revenue",),
                    )
                    try:
                        conn.commit()
                    except Exception:
                        pass
                    break
            except Exception:
                rollback_db_cursor(db)
                infra_ids = []

            if not infra_ids:
                break

            revenue_write_failed = False

            def _row_get(row, key, index=0, default=None):
                if hasattr(row, "get"):
                    return row.get(key, default)
                try:
                    return row[index]
                except (IndexError, TypeError):
                    return default

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
                "integratedsteelmaking": "integrated_steelmaking",
                "electricarcfurnace": "electric_arc_furnace",
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
                    user_id = _row_get(row, "user_id", 0)
                    tech_name = _row_get(row, "name", 1)
                    legacy_key = tech_to_legacy.get(tech_name)
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
                    policies_map[_row_get(row, "user_id", 0)] = _row_get(
                        row, "education", 1, []
                    )

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
                    prov_id = _row_get(row, "province_id", 0)
                    building_name = _row_get(row, "name", 1)
                    quantity = _row_get(row, "quantity", 2, 0)
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
                    stats_map[_row_get(row, "id", 0)] = _row_get(row, "gold", 1, 0)

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
                    user_id = _row_get(row, "user_id", 0)
                    if user_id not in resources_map:
                        resources_map[user_id] = {}
                    resources_map[user_id][_row_get(row, "resource_name", 1)] = _row_get(
                        row, "quantity", 2, 0
                    )

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
                            # Clamp: workforce shortage floors at PRODUCTION_EFFICIENCY_MIN;
                            # workforce surplus does NOT boost production above 1.0.
                            efficiency_multiplier = min(
                                1.0,
                                max(
                                    variables.PRODUCTION_EFFICIENCY_MIN,
                                    employment_ratio,
                                ),
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
                        hs_buildings = int(province_buildings.get("high_school", 0) or 0)
                        uni_buildings = int(province_buildings.get("universities", 0) or 0)
                        # Each school building can graduate 500 students per tick
                        hs_capacity = hs_buildings * 500
                        uni_capacity = uni_buildings * 500
                        school_capacity = hs_capacity + uni_capacity
                        graduates = (
                            min(can_graduate, school_capacity) if school_capacity > 0 else 0
                        )
                        non_graduates = can_graduate - graduates

                        if province_id not in education_deltas:
                            education_deltas[province_id] = {
                                "edu_none": 0,
                                "edu_highschool": 0,
                                "edu_college": 0,
                            }

                        # Distribute graduates: universities first, then high schools
                        if graduates > 0:
                            uni_grads = min(graduates, uni_capacity)
                            hs_grads = min(graduates - uni_grads, hs_capacity)
                            if uni_grads > 0:
                                education_deltas[province_id]["edu_college"] += uni_grads
                            if hs_grads > 0:
                                education_deltas[province_id]["edu_highschool"] += hs_grads

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
                                * variables.DEFAULT_PRODUCTIVITY_PRODUCTION_MULTIPLIER
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

                        # How many of this province's `unit_amount` buildings can
                        # actually afford to run this tick. Partial, not
                        # all-or-nothing: if there's only enough uranium for 7 of
                        # your 10 nuclear reactors, 7 run and produce/consume
                        # normally, 3 sit idle -- rather than every single one
                        # producing nothing because the fleet as a whole came up
                        # short (player-reported real problem: scaling up a
                        # building type made an existing shortfall affect 100% of
                        # output instead of the unaffordable fraction).
                        affordable_units = unit_amount
                        has_enough_stuff = {"status": True, "issues": []}

                        # Pending state — only committed to gold_deductions,
                        # provinces_data energy, and resource_deltas AFTER
                        # affordable_units is finalized, scaled to that count
                        # (not the full unit_amount). Prior versions applied
                        # upkeep before checking energy/resources, so failed
                        # buildings still drained gold and could bankrupt idle
                        # nations (e.g. when a power grid collapse zeroed energy)
                        # -- still true here, just per-unit instead of per-type.
                        pending_gold_cost = 0
                        pending_energy_delta = 0
                        pending_resource_deltas_local = {}

                        cost_per_unit = operating_costs / unit_amount
                        if cost_per_unit > 0:
                            affordable_units = min(
                                affordable_units, int(current_money // cost_per_unit)
                            )
                            if affordable_units < unit_amount:
                                has_enough_stuff["issues"].append("money")

                        # Use tracked energy in provinces_data instead of
                        # per-building SELECT
                        energy_per_unit = 0
                        if unit in energy_consumers:
                            energy_per_unit = 1  # Each unit consumes 1 energy
                        elif unit == "steel_mills" and upgrades.get("electricarcfurnace"):
                            energy_per_unit = 2  # EAF consumes 2 energy per mill

                        if energy_per_unit:
                            prov_data = provinces_data.get(province_id, {})
                            current_energy = prov_data.get("energy", 0)
                            affordable_by_energy = int(current_energy // energy_per_unit)
                            if affordable_by_energy < affordable_units:
                                has_enough_stuff["issues"].append("energy")
                            affordable_units = min(affordable_units, affordable_by_energy)

                        # Use preloaded resources instead of per-building queries
                        resources = resources_map.get(user_id, {})
                        # Resources is now a dict of resource_name -> quantity
                        # (no fallback query needed, all loaded upfront)

                        # Per-unit resource cost, after unit-specific multipliers
                        # (computed once against a single unit, independent of
                        # unit_amount, so it can be scaled by affordable_units
                        # below once every resource's ceiling is known).
                        per_unit_minus = {}
                        for resource, base_amount in minus.items():
                            amount_per_unit = base_amount

                            # AUTOMATION INTEGRATION
                            if unit == "component_factories" and upgrades.get(
                                "automationintegration"
                            ):
                                amount_per_unit *= 0.75
                            # LARGER FORGES
                            if unit == "steel_mills" and upgrades.get("largerforges"):
                                amount_per_unit *= 0.7

                            # INTEGRATED STEELMAKING
                            if unit == "steel_mills" and upgrades.get("integratedsteelmaking"):
                                amount_per_unit *= 1.36

                            # ELECTRIC ARC FURNACE
                            if unit == "steel_mills" and upgrades.get("electricarcfurnace"):
                                amount_per_unit *= 0.5

                            per_unit_minus[resource] = amount_per_unit

                            if amount_per_unit <= 0:
                                continue

                            current_resource = resources.get(resource, 0)
                            # Account for any pending deltas in this run
                            pending_delta = resource_deltas.get(user_id, {}).get(
                                resource, 0
                            )
                            effective_current = current_resource + pending_delta

                            affordable_by_resource = int(
                                effective_current // amount_per_unit
                            )
                            if affordable_by_resource < affordable_units:
                                has_enough_stuff["issues"].append(resource)
                            affordable_units = min(affordable_units, affordable_by_resource)

                        affordable_units = max(0, affordable_units)
                        has_enough_stuff["status"] = affordable_units > 0

                        if not has_enough_stuff["status"]:
                            issues_str = ", ".join(has_enough_stuff["issues"])
                            log_verbose(
                                "F | USER: %s | PROVINCE: %s | %s (%s) | Not enough %s"
                                % (user_id, province_id, unit, unit_amount, issues_str)
                            )
                            continue

                        if affordable_units < unit_amount:
                            issues_str = ", ".join(has_enough_stuff["issues"])
                            log_verbose(
                                "P | USER: %s | PROVINCE: %s | %s (%s/%s) | "
                                "Partial -- short on %s"
                                % (
                                    user_id,
                                    province_id,
                                    unit,
                                    affordable_units,
                                    unit_amount,
                                    issues_str,
                                )
                            )

                        # Scale pending state to how many units actually run,
                        # then commit.
                        if cost_per_unit > 0:
                            pending_gold_cost = int(round(cost_per_unit * affordable_units))
                        if energy_per_unit:
                            pending_energy_delta = -(energy_per_unit * affordable_units)
                        for resource, amount_per_unit in per_unit_minus.items():
                            if amount_per_unit <= 0:
                                continue
                            pending_resource_deltas_local[resource] = (
                                pending_resource_deltas_local.get(resource, 0)
                                - amount_per_unit * affordable_units
                            )

                        if pending_gold_cost:
                            gold_deductions[user_id] = (
                                gold_deductions.get(user_id, 0) + pending_gold_cost
                            )
                        if pending_energy_delta and province_id in provinces_data:
                            provinces_data[province_id]["energy"] = (
                                provinces_data[province_id].get("energy", 0)
                                + pending_energy_delta
                            )
                        if pending_resource_deltas_local:
                            if user_id not in resource_deltas:
                                resource_deltas[user_id] = {}
                            for res_name, delta in pending_resource_deltas_local.items():
                                resource_deltas[user_id][res_name] = (
                                    resource_deltas[user_id].get(res_name, 0) + delta
                                )
                                log_verbose(
                                    "S | MINUS | USER: %s | PROVINCE: %s | %s (%s) | "
                                    "%s delta=%s"
                                    % (
                                        user_id,
                                        province_id,
                                        unit,
                                        affordable_units,
                                        res_name,
                                        delta,
                                    )
                                )

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
                            
                        if unit == "steel_mills":
                            if upgrades.get("integratedsteelmaking"):
                                plus_amount_multiplier += 0.36

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
                            amount *= affordable_units
                            amount += plus_amount
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
                            amount *= affordable_units
                            do_effect(effect, amount, "+")

                        for effect, amount in effminus.items():
                            amount *= affordable_units
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
                
                # Apply Widespread Propaganda: completely nullify unemployment happiness penalty
                if upgrades.get("widespreadpropaganda"):
                    unemployment_penalty = 0
                    
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
                            "UPDATE stats SET gold = GREATEST(gold - %s, 0) WHERE id = %s",
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
                revenue_write_failed = True
                handle_exception(e, "generate_province_revenue")

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
                revenue_write_failed = True
                handle_exception(e, "generate_province_revenue")

            # Resource deltas before education: education failures used to call
            # conn.rollback() and wipe uncommitted province/gold/resource work.
            if revenue_write_failed:
                try:
                    conn.rollback()
                except Exception:
                    pass
            else:
                try:
                    if resource_deltas:
                        resource_updates = []
                        for user_id, deltas in resource_deltas.items():
                            if not deltas:
                                continue
                            for resource_name, delta in deltas.items():
                                if delta != 0:
                                    resource_updates.append(
                                        (user_id, resource_name, delta)
                                    )

                        if resource_updates:
                            resource_names = list(set(r[1] for r in resource_updates))
                            dbdict.execute(
                                "SELECT name, resource_id FROM resource_dictionary "
                                "WHERE name = ANY(%s)",
                                (resource_names,),
                            )
                            resource_id_map = {
                                row["name"]: row["resource_id"]
                                for row in dbdict.fetchall()
                            }

                            batch_values = [
                                (uid, resource_id_map[rname], max(0, delta), delta)
                                for uid, rname, delta in resource_updates
                                if rname in resource_id_map
                            ]

                            if batch_values:
                                execute_batch(
                                    db,
                                    """
                                    INSERT INTO user_economy
                                        (user_id, resource_id, quantity, updated_at)
                                    VALUES (%s, %s, %s, now())
                                    ON CONFLICT (user_id, resource_id)
                                    DO UPDATE SET
                                        quantity = GREATEST(
                                            0, user_economy.quantity + %s
                                        ),
                                        updated_at = now()
                                    """,
                                    batch_values,
                                    page_size=200,
                                )
                                log_verbose(
                                    f"Upserted resources for {len(batch_values)} "
                                    "user+resource pairs"
                                )

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
                    revenue_write_failed = True
                    handle_exception(e, "generate_province_revenue")

            # Education deltas (savepoint so failure does not roll back resources)
            try:
                if education_deltas:
                    edu_updates = []
                    for pid, delta in education_deltas.items():
                        edu_none = max(
                            0, min(int(delta.get("edu_none", 0) or 0), MAX_INT_32)
                        )
                        edu_hs = max(
                            0,
                            min(int(delta.get("edu_highschool", 0) or 0), MAX_INT_32),
                        )
                        edu_col = max(
                            0,
                            min(int(delta.get("edu_college", 0) or 0), MAX_INT_32),
                        )
                        if edu_none or edu_hs or edu_col:
                            edu_updates.append((edu_none, edu_hs, edu_col, pid))
                    if edu_updates:
                        db.execute("SAVEPOINT revenue_education_batch")
                        try:
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
                        except Exception as edu_err:
                            db.execute("ROLLBACK TO SAVEPOINT revenue_education_batch")
                            handle_exception(edu_err)
            except Exception as e:
                handle_exception(e)

            # Final commit (includes resource + province writes; last_run below)
            committed = False
            if revenue_write_failed:
                try:
                    conn.rollback()
                except Exception:
                    pass
            try:
                if not revenue_write_failed:
                    try:
                        conn.commit()
                        committed = True
                    except AttributeError:
                        committed = True
            except Exception as commit_err:
                try:
                    conn.rollback()
                except Exception:
                    pass
                handle_exception(commit_err, "generate_province_revenue")
                committed = False

            if committed:
                any_chunk_committed = True
                try:
                    if all_province_ids:
                        last_processed_pid = max(all_province_ids)
                        db.execute(
                            "UPDATE task_cursors SET last_id=%s WHERE task_name=%s",
                            (last_processed_pid, "generate_province_revenue"),
                        )
                        conn.commit()
                except Exception as e:
                    print(f"Failed to update task cursor: {e}")
            chunks_completed += 1
            if revenue_write_failed:
                break

        duration = time.perf_counter() - start_time
        try:
            from helpers import record_task_metric

            record_task_metric("generate_province_revenue", duration)
        except Exception:
            pass

        print(
            f"generate_province_revenue: processed {processed} provinces in "
            f"{duration:.2f}s chunks={chunks_completed} (skipped={skipped_for_lock})"
        )

        if any_chunk_committed:
            try:
                db.execute(
                    "UPDATE task_runs SET last_run = now() WHERE task_name = %s",
                    ("generate_province_revenue",),
                )
                conn.commit()
            except Exception as e:
                handle_exception(e, "generate_province_revenue")

        try:
            release_pg_advisory_lock(conn, 9002)
        except Exception:
            pass


