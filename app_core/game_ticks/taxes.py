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
from app_core.game_ticks.common import should_skip_task, handle_exception
from app_core.game_ticks.locks import try_pg_advisory_lock, release_pg_advisory_lock
from app_core.game_ticks.food import consumer_goods_distribution_capacity



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

    conn = None
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

            # Load all consumer_goods and rations from normalized user_economy
            cg_map = {}
            rations_map = {}
            dbdict.execute(
                """
                SELECT ue.user_id, rd.name, COALESCE(ue.quantity, 0) AS quantity
                FROM user_economy ue
                JOIN resource_dictionary rd ON rd.resource_id = ue.resource_id
                WHERE ue.user_id = ANY(%s) AND rd.name IN ('consumer_goods', 'rations')
                """,
                (all_user_ids,),
            )
            for row in dbdict.fetchall():
                if isinstance(row, dict):
                    uid = row.get("user_id") or row.get("id") or row.get("Id") or row.get("ID")
                    rname = row.get("name")
                    qty = row.get("quantity") or 0
                else:
                    uid = row[0]
                    rname = row[1]
                    qty = row[2] if len(row) > 2 else 0

                if rname == "consumer_goods":
                    cg_map[uid] = qty
                elif rname == "rations":
                    rations_map[uid] = qty

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
            rations_dist_cap_map = {}
            if variables.FEATURE_DEMOGRAPHIC_CONSUMPTION or variables.FEATURE_RATIONS_DISTRIBUTION:
                dbdict.execute(
                    """
                    SELECT ub.user_id, bd.name, COALESCE(SUM(ub.quantity), 0) AS qty
                    FROM user_buildings ub
                    JOIN building_dictionary bd
                        ON bd.building_id = ub.building_id
                    WHERE ub.user_id = ANY(%s)
                      AND bd.name IN (
                          'distribution_centers', 'food_banks', 'malls',
                          'general_stores', 'gas_stations', 'farmers_markets'
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
                    
                    if variables.FEATURE_DEMOGRAPHIC_CONSUMPTION:
                        cap_cg = variables.CONSUMER_GOODS_DISTRIBUTION_PER_BUILDING.get(
                            bname,
                            0,
                        )
                        if cap_cg > 0:
                            cg_dist_cap_map[uid] = cg_dist_cap_map.get(uid, 0) + qty * cap_cg

                    if variables.FEATURE_RATIONS_DISTRIBUTION:
                        cap_rations = variables.RATIONS_DISTRIBUTION_PER_BUILDING.get(
                            bname,
                            0,
                        )
                        if cap_rations > 0:
                            rations_dist_cap_map[uid] = rations_dist_cap_map.get(uid, 0) + qty * cap_rations

            # Preload coalition membership + tax rates for alliance tax
            coalition_tax_map = {}  # user_id -> (colId, tax_rate)
            try:
                from database import get_coalition_members_table

                members_tbl = get_coalition_members_table()
                if members_tbl:
                    dbdict.execute(
                        f"""
                    SELECT cl.userid, cl.colid, COALESCE(cn.tax_rate, 0) AS tax_rate
                    FROM {members_tbl} cl
                    JOIN colNames cn ON cn.id = cl.colid
                    WHERE cl.userid = ANY(%s) AND COALESCE(cn.tax_rate, 0) > 0
                    """,
                        (all_user_ids,),
                    )
                else:
                    raise RuntimeError("no coalition membership table")
                for row in dbdict.fetchall():
                    if isinstance(row, dict):
                        uid = row.get("userid") or row.get("user_id")
                        coalition_tax_map[uid] = (row.get("colid"), row.get("tax_rate"))
                    else:
                        coalition_tax_map[row[0]] = (row[1], row[2])
            except Exception as e:
                # If colNames doesn't have tax_rate yet (migration pending),
                # just skip coalition taxes this run
                print(f"Coalition tax preload skipped: {e}")
                conn.rollback()

            # Prepare batch updates
            money_updates = []
            cg_updates = []
            coalition_bank_deposits = {}  # colId -> total_gold_to_deposit

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

                # APPLY RATIONS (FOOD) TAX PENALTY
                current_rations = rations_map.get(user_id, 0)
                total_population = sum(p[0] for p in provinces)
                needed_rations = max(int(total_population // variables.RATIONS_PER), 1)
                
                if variables.FEATURE_RATIONS_DISTRIBUTION:
                    r_dist_cap = rations_dist_cap_map.get(user_id, 0)
                    effective_rations = min(current_rations, r_dist_cap)
                else:
                    effective_rations = current_rations
                
                rcp = min(0.0, (effective_rations / needed_rations) - 1.0)
                grace_period = (len(provinces) <= 1) and (sum(p[1] for p in provinces) <= 20)
                if grace_period:
                    food_tax_multiplier = 1.0
                else:
                    food_tax_multiplier = 1.0 + (rcp * (1.0 - variables.NO_FOOD_TAX_MULTIPLIER))
                income *= food_tax_multiplier

                money = int(math.floor(income))

                if not money:
                    continue

                # Alliance tax: deduct % from income and deposit to coalition bank
                tax_deducted = 0
                if user_id in coalition_tax_map:
                    col_id, tax_rate = coalition_tax_map[user_id]
                    tax_deducted = int(money * tax_rate / 100)
                    tax_deducted = min(money, tax_deducted)
                    if tax_deducted > 0:
                        money -= tax_deducted
                        coalition_bank_deposits[col_id] = (
                            coalition_bank_deposits.get(col_id, 0) + tax_deducted
                        )

                msg = (
                    f"Updated money for user id: {user_id}."
                    f" {current_money} -> {current_money + money} (+{money})"
                )
                if tax_deducted:
                    msg += f" [tax: {tax_deducted}]"
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
            # Deposit alliance taxes into coalition banks
            if coalition_bank_deposits:
                tax_updates = [
                    (gold, col_id) for col_id, gold in coalition_bank_deposits.items()
                ]
                try:
                    execute_batch(
                        db,
                        "UPDATE colBanks SET money = money + %s WHERE colId = %s",
                        tax_updates,
                        page_size=50,
                    )
                    total_tax = sum(coalition_bank_deposits.values())
                    print(
                        f"Alliance tax deposited: {total_tax} gold across "
                        f"{len(coalition_bank_deposits)} coalitions"
                    )
                except Exception as e:
                    print(f"Alliance tax deposit failed: {e}")
                    conn.rollback()
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

            committed = False
            try:
                try:
                    conn.commit()
                    committed = True
                except AttributeError:
                    committed = True
            except Exception as e:
                try:
                    conn.rollback()
                except Exception:
                    pass
                handle_exception(e, "tax_income")
                committed = False

            if committed:
                try:
                    db.execute(
                        "UPDATE task_runs SET last_run = now() WHERE task_name = %s",
                        ("tax_income",),
                    )
                    conn.commit()
                except Exception as e:
                    handle_exception(e, "tax_income")

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
                try:
                    conn.rollback()
                except Exception:
                    pass

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




def war_reparation_tax():
    from database import get_db_connection
    from psycopg2.extras import RealDictCursor

    with get_db_connection() as conn:
        db = conn.cursor()
        dbdict = conn.cursor(cursor_factory=RealDictCursor)
        db.execute(
            "SELECT id, peace_date, attacker, attacker_morale, "
            "defender, defender_morale FROM wars WHERE (peace_date IS NOT "
            "NULL) AND (peace_offer_id IS NULL)"
        )
        truces = db.fetchall()

        for state in truces:
            war_id, peace_date, attacker, a_morale, defender, d_morale = state

            # Remove peace records older than one week (604800 seconds)
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

                db.execute("SELECT war_type FROM wars WHERE id=%s", (war_id,))
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


