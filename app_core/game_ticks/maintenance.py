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

# War supplies started at a fixed 200 per side and nothing ever refilled them
# (Discord report: "no matter how many troops I send, it keeps telling me I
# have no supplies" — once spent, attacks were permanently blocked for that
# war). Organized Supply Lines has always been described as "further
# increasing war supplies production by 15%", implying base regen that was
# never implemented. Add a modest hourly trickle, capped so a dormant war
# doesn't stockpile indefinitely.
WAR_SUPPLY_REGEN_PER_HOUR = int(os.getenv("WAR_SUPPLY_REGEN_PER_HOUR", "20"))
WAR_SUPPLY_CAP = int(os.getenv("WAR_SUPPLY_CAP", "2000"))
WAR_SUPPLY_LINES_BONUS = 1.15

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

def backfill_missing_resources():
    from database import get_db_connection

    # Clean up stale user-linked rows first so backfill never tries to
    # operate around orphaned records from deleted users.
    cleanup_orphan_user_rows()

    with get_db_connection() as conn:
        db = conn.cursor()
        
        # 1. Backfill stats
        db.execute(
            """
            INSERT INTO stats (id, location, gold)
            SELECT u.id, 'Grassland', 80000000
            FROM users u
            LEFT JOIN stats s ON u.id = s.id
            WHERE s.id IS NULL
            ON CONFLICT DO NOTHING
            """
        )
        stats_inserted = db.rowcount
        
        # 2. Backfill policies
        db.execute(
            """
            INSERT INTO policies (user_id)
            SELECT u.id
            FROM users u
            LEFT JOIN policies p ON u.id = p.user_id
            WHERE p.user_id IS NULL
            ON CONFLICT DO NOTHING
            """
        )
        policies_inserted = db.rowcount
        
        # 3. Backfill user_military (init to 0)
        db.execute(
            """
            INSERT INTO user_military (user_id, unit_id, quantity)
            SELECT u.id, ud.unit_id, 0
            FROM users u
            CROSS JOIN unit_dictionary ud
            WHERE ud.is_active = TRUE
            ON CONFLICT DO NOTHING
            """
        )
        military_inserted = db.rowcount

        # 4. Backfill user_economy
        db.execute(
            """
            INSERT INTO user_economy (user_id, resource_id, quantity)
            SELECT u.id, rd.resource_id, 0
            FROM users u
            CROSS JOIN resource_dictionary rd
            ON CONFLICT DO NOTHING
            """
        )
        economy_inserted = db.rowcount
        
        if stats_inserted or policies_inserted or military_inserted or economy_inserted:
            print(f"Backfill complete: stats={stats_inserted}, policies={policies_inserted}, military={military_inserted}, economy={economy_inserted}")

        conn.commit()




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




# =============================================================================
# TRADE AGREEMENTS - Automatic recurring trades
# =============================================================================


def execute_due_trade_agreements():
    """Find and execute all trade agreements that are due."""
    import time
    import traceback
    from app_core.trade_agreements.services import execute_trade_agreement
    from database import get_db_connection

    start_time = time.perf_counter()

    with get_db_connection() as conn:
        if not try_pg_advisory_lock(conn, 9004, "execute_trade_agreements"):
            return
        db = conn.cursor()

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
            try:
                conn.rollback()
            except Exception:
                pass




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
            # global_tick fires every 10 min, but military maintenance costs are
            # calibrated per HOUR (matching hourly production in
            # generate_province_revenue). Gate the deduction to once per hour so
            # armies aren't charged 6x their intended upkeep (which was silently
            # starving any nation with a standing army — player-reported).
            consumption_start = time.time()
            db.execute(
                "INSERT INTO task_runs (task_name, last_run) VALUES (%s, NULL) "
                "ON CONFLICT DO NOTHING",
                ("military_maintenance",),
            )
            db.execute(
                "SELECT last_run FROM task_runs WHERE task_name=%s FOR UPDATE",
                ("military_maintenance",),
            )
            maint_row = db.fetchone()
            run_maintenance = not should_skip_task(maint_row, "military_maintenance")

            cost_rows = []
            if run_maintenance:
                db.execute(
                    "UPDATE task_runs SET last_run = now() WHERE task_name = %s",
                    ("military_maintenance",),
                )
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

            # -----------------------------------------------------------------
            # War supply regeneration phase (hourly, see WAR_SUPPLY_* above)
            # -----------------------------------------------------------------
            supply_start = time.time()
            db.execute(
                "INSERT INTO task_runs (task_name, last_run) VALUES (%s, NULL) "
                "ON CONFLICT DO NOTHING",
                ("war_supply_regen",),
            )
            db.execute(
                "SELECT last_run FROM task_runs WHERE task_name=%s FOR UPDATE",
                ("war_supply_regen",),
            )
            supply_row = db.fetchone()
            if not should_skip_task(supply_row, "war_supply_regen"):
                db.execute(
                    "UPDATE task_runs SET last_run = now() WHERE task_name = %s",
                    ("war_supply_regen",),
                )
                dbdict.execute(
                    """
                    SELECT id, attacker, defender, attacker_supplies, defender_supplies
                    FROM wars
                    WHERE status = 'active'
                      AND (attacker_supplies < %s OR defender_supplies < %s)
                    """,
                    (WAR_SUPPLY_CAP, WAR_SUPPLY_CAP),
                )
                active_wars = dbdict.fetchall()
                if active_wars:
                    combatant_ids = sorted(
                        {w["attacker"] for w in active_wars}
                        | {w["defender"] for w in active_wars}
                    )
                    dbdict.execute(
                        """
                        SELECT ut.user_id FROM user_tech ut
                        JOIN tech_dictionary td ON td.tech_id = ut.tech_id
                        WHERE ut.user_id = ANY(%s) AND ut.is_unlocked = TRUE
                          AND td.name = 'organized_supply_lines'
                        """,
                        (combatant_ids,),
                    )
                    supply_lines_users = {row["user_id"] for row in dbdict.fetchall()}

                    supply_updates = []
                    for w in active_wars:
                        atk_rate = WAR_SUPPLY_REGEN_PER_HOUR * (
                            WAR_SUPPLY_LINES_BONUS
                            if w["attacker"] in supply_lines_users
                            else 1.0
                        )
                        def_rate = WAR_SUPPLY_REGEN_PER_HOUR * (
                            WAR_SUPPLY_LINES_BONUS
                            if w["defender"] in supply_lines_users
                            else 1.0
                        )
                        new_attacker = min(
                            WAR_SUPPLY_CAP, w["attacker_supplies"] + round(atk_rate)
                        )
                        new_defender = min(
                            WAR_SUPPLY_CAP, w["defender_supplies"] + round(def_rate)
                        )
                        if (
                            new_attacker != w["attacker_supplies"]
                            or new_defender != w["defender_supplies"]
                        ):
                            supply_updates.append((new_attacker, new_defender, w["id"]))

                    if supply_updates:
                        execute_batch(
                            db,
                            "UPDATE wars SET attacker_supplies=%s, "
                            "defender_supplies=%s WHERE id=%s",
                            supply_updates,
                            page_size=500,
                        )

            supply_phase_ms = int((time.time() - supply_start) * 1000)
            if supply_phase_ms > 30000:
                logger.warning(f"War supply regen phase exceeded 30s: {supply_phase_ms}ms")

            total_duration_ms = int((time.time() - tick_start) * 1000)
            if total_duration_ms > 30000:
                logger.warning(f"Global tick exceeded 30s total: {total_duration_ms}ms")

            # --- Spawning Interactive Events ---
            try:
                import random
                import json
                import os
                events_path = os.path.join(os.path.dirname(__file__), 'app_core', 'events', 'events.json')
                if os.path.exists(events_path):
                    with open(events_path, 'r') as f:
                        events_data = json.load(f)
                    if events_data:
                        event_ids = list(events_data.keys())
                        db.execute("""
                            SELECT u.id, COUNT(p.id) 
                            FROM users u 
                            JOIN provinces p ON p.userId = u.id 
                            WHERE u.last_active >= NOW() - INTERVAL '3 days'
                            GROUP BY u.id
                        """)
                        rows = db.fetchall()
                        inserts = []
                        base_chance = 0.30  # 30% chance per province per tick
                        for row in rows:
                            user_id = row[0]
                            province_count = row[1]
                            
                            # Check if they already have an unresolved event
                            db.execute("SELECT 1 FROM interactive_events WHERE user_id = %s AND resolved_at IS NULL", (user_id,))
                            if db.fetchone():
                                continue
                                
                            spawned = False
                            for _ in range(province_count):
                                if random.random() < base_chance:
                                    spawned = True
                                    break
                                    
                            if spawned:
                                event_id = random.choice(event_ids)
                                inserts.append((user_id, event_id))
                                
                        if inserts:
                            from psycopg2.extras import execute_batch
                            execute_batch(db, "INSERT INTO interactive_events (user_id, event_def_id) VALUES (%s, %s)", inserts)
            except Exception as ev_err:
                logger.warning(f"Failed to spawn interactive events: {ev_err}")
            # -----------------------------------

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
                conn.rollback() # MUST rollback the poisoned transaction first!
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
                pass
            handle_exception(e)
            raise
        finally:
            try:
                release_pg_advisory_lock(conn, 9010)
            except Exception:
                pass


