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

# Re-exported moved names
from app_core.game_ticks.common import should_skip_task, is_task_stale, handle_exception, log_verbose, _safe_update_productivity, _run_with_deadlock_retries, MAX_INT_32
from app_core.game_ticks.locks import try_pg_advisory_lock, release_pg_advisory_lock, _get_redis_client, leader_only, _redis_pool, _delete_lock_lua
from app_core.game_ticks.food import rations_needed, rations_distribution_capacity, food_stats, compute_rations_distribution_cap, nation_distribution_status, fetch_nation_distribution_status, consumer_goods_distribution_capacity, calculate_demographic_rations_need, calculate_demographic_consumer_goods_need
from app_core.game_ticks.energy import energy_info, energy_stats
from app_core.game_ticks.taxes import calc_ti, tax_income, war_reparation_tax
from app_core.game_ticks.population import population_growth, calculate_workforce_available, apply_workforce_hiring_and_debuffs, find_unit_category
from app_core.game_ticks.revenue import generate_province_revenue
from app_core.game_ticks.disasters import run_natural_disasters
from app_core.game_ticks.maintenance import backfill_missing_resources, cleanup_orphan_user_rows, refresh_bot_offers, market_bot_fight_wars, execute_due_trade_agreements, _create_game_tick_log, _finalize_game_tick_log, global_tick, BOT_USER_ID, BOT_OFFERS




"""
Tested features:
- resource giving
- unit with enough resources selection
- energy didnt change
- removal of resources
- good monetary removal
"""


# Leader-only decorator to avoid duplicate scheduled task executions
# when multiple beat/scheduler instances are active (e.g., autoscaling).
# It attempts to acquire a short-lived Redis lock and skips execution if
# another instance holds the lock.



@celery.task()
@leader_only(ttl_seconds=300)
def task_population_growth():
    _run_with_deadlock_retries(population_growth, "population_growth")


@celery.task()
@leader_only(ttl_seconds=300)
def task_tax_income():
    _run_with_deadlock_retries(tax_income, "tax_income")


@celery.task()
@leader_only(ttl_seconds=300)
def task_generate_province_revenue():
    _run_with_deadlock_retries(generate_province_revenue, "generate_province_revenue")


@celery.task()
@leader_only(ttl_seconds=300)
def task_natural_disasters():
    _run_with_deadlock_retries(run_natural_disasters, "natural_disasters")


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

        # Manpower tracks a moving target tied to current population (the
        # eligible military-age pool), rather than accumulating forever.
        # Each tick it moves partway toward that target in either direction:
        # up when population has grown and there's room to recruit more,
        # down when population has shrunk (attrition/aging out of the
        # reserve), instead of only ever increasing until spent.
        ADJUSTMENT_RATE = 0.15
        ELIGIBLE_POOL_FRACTION = 0.2

        manpower_updates = []
        for user_id in user_ids:
            population = pop_map.get(user_id)
            if not population:
                continue

            target_manpower = float(population) * ELIGIBLE_POOL_FRACTION
            manpower = manpower_map.get(user_id, 0)
            delta = int((target_manpower - manpower) * ADJUSTMENT_RATE)

            if delta != 0:
                manpower_updates.append((delta, user_id))

        # Batch update all manpower at once
        if manpower_updates:
            execute_batch(
                db,
                "UPDATE stats SET manpower = GREATEST(0, manpower + %s) WHERE id=%s",
                manpower_updates,
                page_size=100,
            )
        conn.commit()


@celery.task
@leader_only(ttl_seconds=300)
def task_refresh_bot_offers():
    """Celery task to refresh bot market offers every 5 minutes."""
    _run_with_deadlock_retries(refresh_bot_offers, "refresh_bot_offers")
    _run_with_deadlock_retries(market_bot_fight_wars, "market_bot_fight_wars")

@celery.task()
@leader_only(ttl_seconds=300)
def task_backfill_missing_resources():
    _run_with_deadlock_retries(backfill_missing_resources, "backfill_missing_resources")


@celery.task()
@leader_only(ttl_seconds=300)
def task_cleanup_orphan_user_rows():
    _run_with_deadlock_retries(cleanup_orphan_user_rows, "cleanup_orphan_user_rows")


@celery.task(name="tasks.task_patreon_gem_grant")
@leader_only(ttl_seconds=300)
def task_patreon_gem_grant():
    """Monthly Patreon -> Gems bonus. See app_core/patreon/service.py."""
    from app_core.patreon import service as patreon_service

    _run_with_deadlock_retries(patreon_service.run, "patreon_gem_grant")


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


# ---------------------------------------------------------------------------
# AI Agent task
# ---------------------------------------------------------------------------


@celery.task(name="tasks.task_update_war_supplies")
def task_update_war_supplies():
    """Regenerate war supplies for all active wars (50 supply/hour per side).

    Previously this was only triggered when a player visited the war page, which
    meant supplies never ticked for players who weren't actively checking.  This
    task runs hourly so supplies regenerate regardless of page visits.
    """
    try:
        from wars.service import update_supply
        from database import get_db_connection

        with get_db_connection() as conn:
            cur = conn.cursor()
            # peace_date is stored as a real (epoch seconds), not a timestamp,
            # so compare against EXTRACT(EPOCH FROM NOW()).
            cur.execute(
                "SELECT id FROM wars WHERE peace_date IS NULL "
                "OR peace_date > EXTRACT(EPOCH FROM NOW())"
            )
            active_war_ids = [row[0] for row in cur.fetchall()]

        updated = 0
        errors = 0
        for war_id in active_war_ids:
            try:
                update_supply(war_id)
                updated += 1
            except Exception as e:
                print(f"task_update_war_supplies: war {war_id} failed — {e}")
                errors += 1

        print(f"task_update_war_supplies: updated {updated} wars, {errors} errors")
    except Exception as e:
        print(f"task_update_war_supplies: fatal — {e}")


@celery.task(name="tasks.task_ai_agent")
def task_ai_agent():
    """Run the AI nation agent for configured user(s).

    Disabled by default — set AI_AGENT_ENABLED=1 and AI_AGENT_PASSWORD
    in environment to activate.
    """
    if os.getenv("AI_AGENT_ENABLED") != "1":
        return

    try:
        from ai_agent import run_ai_agent

        result = run_ai_agent()
        print(f"ai_agent: completed — {result}")
    except Exception as e:
        print(f"ai_agent: failed — {e}")
