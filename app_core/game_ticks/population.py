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

def calc_education_graduation(pop_children, policies, primary_buildings, hs_buildings, uni_buildings, now=None):
    """Computes tier-chained education graduation for a province. Shared between tick and display."""
    from datetime import datetime, timezone
    
    graduation_rate = variables.DEMO_AGING_RATES["children_to_working"]
    if variables.POLICY_MANDATORY_SCHOOLING in policies:
        graduation_rate *= variables.POLICY_SCHOOLING_GRADUATION_MULTIPLIER

    can_graduate = min(pop_children, int(round(pop_children * graduation_rate)))
    
    true_primary_capacity = primary_buildings * 500
    hs_capacity = hs_buildings * 900
    uni_capacity = uni_buildings * 5000
    
    primary_capacity = true_primary_capacity
    grace_until = None
    
    raw_grace = getattr(variables, "EDUCATION_CHAIN_GRACE_UNTIL", "")
    if raw_grace:
        try:
            grace_dt = datetime.fromisoformat(raw_grace)
            now_dt = now or datetime.now(timezone.utc)
            if now_dt < grace_dt:
                grace_until = grace_dt
                primary_capacity = max(primary_capacity, hs_capacity + uni_capacity)
        except ValueError:
            pass

    passed_primary = min(can_graduate, primary_capacity)
    passed_hs = min(passed_primary, hs_capacity)
    passed_uni = min(passed_hs, uni_capacity)

    return {
        "can_graduate": can_graduate,
        "passed_primary": passed_primary,
        "passed_hs": passed_hs,
        "passed_uni": passed_uni,
        "edu_college_new": passed_uni,
        "edu_highschool_new": passed_hs - passed_uni,
        "edu_none_new": can_graduate - passed_hs,
        "primary_capacity": primary_capacity,
        "true_primary_capacity": true_primary_capacity,
        "hs_capacity": hs_capacity,
        "uni_capacity": uni_capacity,
        "grace_until": grace_until

    }


def nation_comfort(total_cities, total_land, happiness=50, pollution=50):
    """Comfortable population for a whole nation (NOT per province -- see
    variables.NATION_COMFORT_BASE for why). Saturating curve on total
    cities/land, scaled by the nation's population-weighted happiness and
    pollution the same way the old per-province max population was."""
    c = max(0.0, float(total_cities or 0))
    l = max(0.0, float(total_land or 0))
    comfort = (
        variables.NATION_COMFORT_BASE
        + variables.CITY_POP_CAP * (1 - math.exp(-c / variables.CITY_POP_SOFTNESS))
        + variables.LAND_POP_CAP * (1 - math.exp(-l / variables.LAND_POP_SOFTNESS))
    )
    happiness_multiplier = (
        (happiness - 50) * variables.DEFAULT_HAPPINESS_GROWTH_MULTIPLIER / 50
    )
    pollution_multiplier = (
        (pollution - 50) * -variables.DEFAULT_POLLUTION_GROWTH_MULTIPLIER / 50
    )
    comfort = int(comfort * (1 + happiness_multiplier + pollution_multiplier))
    return max(variables.NATION_COMFORT_BASE, comfort)


def overcrowding_efficiency(nation_population, comfort):
    """Share of their normal capacity distribution buildings still serve.
    1.0 up to comfort, then sqrt(comfort / population): 4x over comfort =
    50%, so a huge nation needs far more distribution to stay fed."""
    pop = float(nation_population or 0)
    if comfort <= 0 or pop <= comfort:
        return 1.0
    return math.sqrt(comfort / pop)


def distribution_fix_active(now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    return now >= variables.DISTRIBUTION_FIX_START


def distributable_rations(warehouse, dist_cap, nation_population, comfort, now=None):
    """Rations that can actually reach people this tick.

    dist_cap is in PEOPLE served (RATIONS_DISTRIBUTION_PER_BUILDING), the
    warehouse is in RATIONS. Before DISTRIBUTION_FIX_START this keeps the old
    (buggy) min(warehouse, people) comparison, which almost never limited
    anything; after it, covered people are converted to rations and shrunk
    by overcrowding_efficiency()."""
    warehouse = max(0, int(warehouse or 0))
    if dist_cap is None:
        return warehouse
    if not distribution_fix_active(now):
        return min(warehouse, dist_cap)
    covered_people = dist_cap * overcrowding_efficiency(nation_population, comfort)
    return min(warehouse, int(covered_people // variables.RATIONS_PER))


def calc_nation_growth(nation_population, comfort, rations_ratio, frozen=False):
    """People added to a whole nation this tick (before starvation).
    Based on the population the nation actually has, so war deaths slow it
    down; slows to POP_GROWTH_DIMINISHING_FLOOR past comfort (no hard cap).
    Small nations well below comfort grow up to 3x (POP_GROWTH_CATCHUP_*).
    A nation that recently lost a battle / was nuked is frozen (0)."""
    if frozen:
        return 0
    rations_ratio = min(1.0, max(0.0, float(rations_ratio or 0)))
    pop = max(0, int(nation_population or 0))
    pop_ratio = pop / comfort if comfort > 0 else 1
    diminishing = max(variables.POP_GROWTH_DIMINISHING_FLOOR, 1 - pop_ratio**2)
    catchup = 1 + (
        variables.POP_GROWTH_CATCHUP_BOOST
        * max(0.0, 1 - pop_ratio)
        * max(0.0, 1 - pop / variables.POP_GROWTH_CATCHUP_POP)
    )
    raw = (
        variables.POP_GROWTH_RATE * catchup * pop
        + variables.POP_GROWTH_SEED_RATE * comfort
    )
    return int(round((rations_ratio**2) * diminishing * raw))


def province_capacity_weight(cities, land):
    """How a nation's growth is shared between its provinces: by how much
    room each one has (cities/land), so new provinces fill up over time."""
    return (
        variables.DEFAULT_MAX_POPULATION
        + (cities or 0) * variables.CITY_MAX_POPULATION_ADDITION
        + (land or 0) * variables.LAND_MAX_POPULATION_ADDITION
    )


def build_nation_contexts(province_rows):
    """Aggregate province rows (dicts with userid, population, citycount,
    land, happiness, pollution) into per-nation totals + comfort."""
    agg = {}
    for row in province_rows:
        uid = row["userid"]
        pop = int(row.get("population") or 0)
        a = agg.setdefault(
            uid,
            {"pop": 0, "cities": 0, "land": 0, "provinces": 0,
             "happy_w": 0.0, "poll_w": 0.0, "weight": 0},
        )
        a["pop"] += pop
        a["cities"] += int(row.get("citycount") or 0)
        a["land"] += int(row.get("land") or 0)
        a["provinces"] += 1
        a["happy_w"] += pop * float(row.get("happiness") or 0)
        a["poll_w"] += pop * float(row.get("pollution") or 0)
        a["weight"] += province_capacity_weight(row.get("citycount"), row.get("land"))
    for a in agg.values():
        happiness = a["happy_w"] / a["pop"] if a["pop"] else 50
        pollution = a["poll_w"] / a["pop"] if a["pop"] else 50
        a["comfort"] = nation_comfort(a["cities"], a["land"], happiness, pollution)
    return agg


def load_frozen_users(cursor, user_ids):
    """User ids whose growth is frozen right now (population_growth_freezes,
    migration 0106). Empty set if the table doesn't exist yet."""
    cursor.execute("SELECT to_regclass('population_growth_freezes') IS NOT NULL")
    row = cursor.fetchone()
    exists = row[0] if not isinstance(row, dict) else list(row.values())[0]
    if not exists or not user_ids:
        return set()
    cursor.execute(
        "SELECT user_id FROM population_growth_freezes "
        "WHERE user_id = ANY(%s) AND frozen_until > now()",
        (list(user_ids),),
    )
    out = set()
    for r in cursor.fetchall():
        out.add(r["user_id"] if isinstance(r, dict) else r[0])
    return out


def calc_province_population_delta(
    curPop, nation_growth, weight_share, rations_ratio, grace_period
):
    """Net population change for one province this tick: its share of the
    nation's growth minus starvation (up to 1%/h at 0 rations coverage).
    Shared by the tick and the nation-page projection (get_population_growth)
    so the two can't drift apart."""
    growth = int(round(nation_growth * max(0.0, min(1.0, weight_share))))
    rations_ratio = min(1.0, max(0.0, float(rations_ratio or 0)))
    starvation_deaths = 0
    if rations_ratio < 1.0 and not grace_period:
        starvation_deaths = int(round((curPop or 0) * (1.0 - rations_ratio) * 0.01))
    return growth - starvation_deaths


def get_population_growth(cId, db=None):
    """Read-only projection of this tick's population growth for one
    nation, for display on the nation page (Discord suggestion from
    Kurai, 2026-09-21: surface growth rate so players know when to build
    more retail/distribution buildings).

    There is no persisted growth-rate value anywhere -- population_growth()
    above computes it transiently, per province, per tick, and only ever
    writes the resulting new `population` (see that function's docstring
    trail). So this recomputes the same formula for just this nation's
    provinces, using calc_province_population_delta() (the same function
    the real tick calls) so the two can never silently drift apart.

    Returns {"delta": int, "percent": float, "current_population": int,
    "per_province": {str(province_id): int delta}}.
    Cached like get_revenue()/get_econ_statistics() since it does a
    handful of extra queries; invalidated by invalidate_user_cache()
    alongside those (see database.py) so a new distribution building
    shows up in the projection right away instead of up to 5 minutes late.
    """
    from database import reuse_or_new_cursor, query_cache

    cache_key = f"pop_growth_{cId}"
    cached = query_cache.get(cache_key)
    if cached is not None:
        return cached

    with reuse_or_new_cursor(db, read_only=True) as active_db:
        active_db.execute(
            """
            SELECT population, citycount, land, happiness, pollution, id
            FROM provinces WHERE userId = %s
            """,
            (cId,),
        )
        province_rows = active_db.fetchall()

        if not province_rows:
            result = {
                "delta": 0,
                "percent": 0.0,
                "current_population": 0,
                "per_province": {},
            }
            query_cache.set(cache_key, result)
            return result

        rows = [
            {
                "userid": cId,
                "population": r[0] or 0,
                "citycount": r[1] or 0,
                "land": r[2] or 0,
                "happiness": r[3] or 0,
                "pollution": r[4] or 0,
                "id": r[5],
            }
            for r in province_rows
        ]
        nation = build_nation_contexts(rows)[cId]
        grace_period = (nation["provinces"] <= 1) and (nation["land"] <= 20)

        # Same (non-demographic-weighted) rations need as population_growth().
        total_needed = 0
        for row in rows:
            needed = row["population"] // variables.RATIONS_PER
            total_needed += needed if needed >= 1 else 1

        active_db.execute(
            """
            SELECT COALESCE(ue.quantity, 0)
            FROM user_economy ue
            JOIN resource_dictionary rd ON rd.resource_id = ue.resource_id
            WHERE ue.user_id = %s AND rd.name = 'rations'
            """,
            (cId,),
        )
        rations_row = active_db.fetchone()
        rations_warehouse = (rations_row[0] if rations_row else 0) or 0

        dist_cap = None
        if variables.FEATURE_RATIONS_DISTRIBUTION:
            active_db.execute(
                """
                SELECT bd.name, COALESCE(SUM(ub.quantity), 0) AS qty
                FROM user_buildings ub
                JOIN building_dictionary bd ON bd.building_id = ub.building_id
                WHERE ub.user_id = %s AND bd.name = ANY(%s)
                GROUP BY bd.name
                """,
                (cId, list(variables.RATIONS_DISTRIBUTION_BUILDINGS)),
            )
            dist_cap = 0
            for bname, qty in active_db.fetchall():
                cap = variables.RATIONS_DISTRIBUTION_PER_BUILDING.get(
                    bname, variables.RATIONS_DISTRIBUTION_PER_BUILDING_DEFAULT
                )
                dist_cap += (qty or 0) * cap

        effective_rations = distributable_rations(
            rations_warehouse, dist_cap, nation["pop"], nation["comfort"]
        )
        rations_ratio = (
            effective_rations / total_needed if total_needed > 0 else 0
        )
        frozen = cId in load_frozen_users(active_db, [cId])
        nation_growth = calc_nation_growth(
            nation["pop"], nation["comfort"], rations_ratio, frozen=frozen
        )

        total_delta = 0
        per_province = {}
        for row in rows:
            share = (
                province_capacity_weight(row["citycount"], row["land"])
                / nation["weight"]
                if nation["weight"]
                else 0
            )
            province_delta = calc_province_population_delta(
                curPop=row["population"],
                nation_growth=nation_growth,
                weight_share=share,
                rations_ratio=rations_ratio,
                grace_period=grace_period,
            )
            per_province[str(row["id"])] = int(province_delta)
            total_delta += province_delta

        current_population = nation["pop"]
        percent = (
            (total_delta / current_population) * 100 if current_population > 0 else 0.0
        )

        result = {
            "delta": int(total_delta),
            "percent": percent,
            "current_population": int(current_population),
            "per_province": per_province,
            "comfort": int(nation["comfort"]),
            "growth_frozen": frozen,
        }
        query_cache.set(cache_key, result)
        return result


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

        # Nation-level comfort / growth (2026-10-04 rebalance): computed once
        # per nation, then shared out to provinces by capacity weight.
        nation_ctx = build_nation_contexts(all_provinces)

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
        # Rations-storage buffer: every distribution building contributes,
        # scaled the same way it scales consumption capacity, so the buffer
        # reflects total distribution investment regardless of building mix.
        storage_buffer_map = {}
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
                storage_cap = variables.RATIONS_STORAGE_PER_BUILDING.get(
                    bname, variables.RATIONS_STORAGE_PER_BUILDING_DEFAULT
                )
                storage_buffer_map[uid] = (
                    storage_buffer_map.get(uid, 0) + qty * storage_cap
                )

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
            nation = nation_ctx.get(uid) or {"pop": 0, "comfort": 1}
            dist_cap = (
                dist_cap_map.get(uid, 0)
                if variables.FEATURE_RATIONS_DISTRIBUTION
                else None
            )
            distributable = distributable_rations(
                warehouse, dist_cap, nation["pop"], nation["comfort"]
            )
            actually_consumed = min(needed, distributable)
            user_effective_rations[uid] = distributable

            # Rations spoilage: a banked surplus above the buffer decays each
            # hour instead of being able to sustain unattended growth
            # indefinitely. Buffer = free baseline (days of this user's
            # current hourly need) + extra capacity from distribution
            # buildings they've built.
            spoilage = 0
            if not in_spoilage_grace_period:
                buffer = (
                    needed * 24 * variables.RATIONS_BASELINE_BUFFER_DAYS
                    + storage_buffer_map.get(uid, 0)
                )
                remaining_after_consumption = warehouse - actually_consumed
                if remaining_after_consumption > buffer:
                    excess = remaining_after_consumption - buffer
                    spoilage = int(round(excess * variables.RATIONS_EXCESS_DECAY_RATE))

            user_rations_to_deduct[uid] = actually_consumed + spoilage

        frozen_users = load_frozen_users(db, all_user_ids)
        nation_growth_map = {}
        for uid, nation in nation_ctx.items():
            total_needed = user_total_rations_needed.get(uid, 1)
            effective_rations = user_effective_rations.get(uid, 0) or 0
            ratio = effective_rations / total_needed if total_needed > 0 else 0
            nation["rations_ratio"] = ratio
            nation_growth_map[uid] = calc_nation_growth(
                nation["pop"], nation["comfort"], ratio, frozen=uid in frozen_users
            )

        def calc_population_growth(province_row):
            """New population for one province: its capacity-weighted share
            of the nation's growth minus starvation (same math as the
            nation-page projection, get_population_growth)."""
            user_id = province_row["userid"]
            curPop = province_row["population"] or 0
            nation = nation_ctx[user_id]
            grace_period = (user_total_provinces.get(user_id, 1) <= 1) and (user_total_land.get(user_id, 1) <= 20)
            share = (
                province_capacity_weight(province_row["citycount"], province_row["land"])
                / nation["weight"]
                if nation["weight"]
                else 0
            )
            delta = calc_province_population_delta(
                curPop=curPop,
                nation_growth=nation_growth_map.get(user_id, 0),
                weight_share=share,
                rations_ratio=nation.get("rations_ratio", 0),
                grace_period=grace_period,
            )
            fullPop = int(curPop + delta)
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




def calc_unemployment_rate(pop_working, workers_on_record):
    """Share of the working-age population that can't be counted as a worker.

    Working-age people with no education record are still workers (uneducated
    ones). Education buckets only grow on graduation, so treating unrecorded
    people as unemployed made most growing nations look >30% jobless and
    pinned their happiness at 3%/8% (2026-10-05)."""
    if pop_working <= 0:
        return 0.0
    workers = max(workers_on_record, pop_working)
    return max(0.0, 1.0 - workers / pop_working)


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
            unemployment_rate = calc_unemployment_rate(total_pop_working, jobs_available)

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


