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

# Bot market offers configuration
BOT_USER_ID = 9999  # Market Bot account

BOT_OFFERS = [
    # (type, resource, amount, price)
    # Prices set at ~2.5x production cost — bot is a convenience backstop,
    # not a cheap alternative to building your own economy.
    # === SELL offers — processed goods ===
    ("sell", "consumer_goods", 200000, 2500),  # 200k CG @ 5,000 gold
    ("sell", "rations", 500000, 300),  # 500k rations @ 600 gold
    ("sell", "steel", 100000, 6000),  # 100k steel @ 12,000 gold
    ("sell", "aluminium", 50000, 3500),  # 50k aluminium @ 7,000 gold
    ("sell", "components", 25000, 12500),  # 25k components @ 25,000 gold
    # === SELL offers — raw resources for early-game players ===
    ("sell", "coal", 300000, 200),  # 300k coal @ 400 gold
    ("sell", "iron", 300000, 750),  # 300k iron @ 1,500 gold
    ("sell", "lumber", 300000, 300),  # 300k lumber @ 600 gold
    ("sell", "oil", 200000, 600),  # 200k oil @ 1,200 gold
    ("sell", "copper", 200000, 300),  # 200k copper @ 600 gold
    ("sell", "bauxite", 200000, 600),  # 200k bauxite @ 1,200 gold
    # === BUY offers — bot buys surplus from players (~50% of sell price) ===
    ("buy", "coal", 500000, 100),  # buy 500k coal @ 200 gold
    ("buy", "iron", 500000, 350),  # buy 500k iron @ 700 gold
    ("buy", "lumber", 500000, 150),  # buy 500k lumber @ 300 gold
    ("buy", "oil", 500000, 300),  # buy 500k oil @ 600 gold
    ("buy", "copper", 500000, 150),  # buy 500k copper @ 300 gold
    ("buy", "bauxite", 500000, 300),  # buy 500k bauxite @ 600 gold
]


def refresh_bot_offers():
    """Delete old bot offers and create fresh ones for essential resources."""
    from database import get_db_connection

    with get_db_connection() as conn:
        db = conn.cursor()

        # Delete ALL existing bot offers first (cleans up stale/removed offers)
        db.execute("DELETE FROM offers WHERE user_id = %s", (BOT_USER_ID,))

        for offer_type, resource, amount, price in BOT_OFFERS:
            db.execute(
                "INSERT INTO offers (user_id, type, resource, amount, price) "
                "VALUES (%s, %s, %s, %s, %s)",
                (BOT_USER_ID, offer_type, resource, amount, price),
            )

        print(f"Bot offers refreshed: {len(BOT_OFFERS)} offers created")


def market_bot_fight_wars():
    """Market Bot (ID 9999) automatically fights anyone it's at war with."""


# Bot market offers configuration
BOT_USER_ID = 9999  # Market Bot account

BOT_USER_ID = 9999  # Market Bot account
BOT_OFFERS = [
    # (type, resource, amount, price)
    # Prices set at ~2.5x production cost — bot is a convenience backstop,
    # not a cheap alternative to building your own economy.
    # === SELL offers — processed goods ===
    ("sell", "consumer_goods", 200000, 2500),  # 200k CG @ 5,000 gold
    ("sell", "rations", 500000, 300),  # 500k rations @ 600 gold
    ("sell", "steel", 100000, 6000),  # 100k steel @ 12,000 gold
    ("sell", "aluminium", 50000, 3500),  # 50k aluminium @ 7,000 gold
    ("sell", "components", 25000, 12500),  # 25k components @ 25,000 gold
    # === SELL offers — raw resources for early-game players ===
    ("sell", "coal", 300000, 200),  # 300k coal @ 400 gold
    ("sell", "iron", 300000, 750),  # 300k iron @ 1,500 gold
    ("sell", "lumber", 300000, 300),  # 300k lumber @ 600 gold
    ("sell", "oil", 200000, 600),  # 200k oil @ 1,200 gold
    ("sell", "copper", 200000, 300),  # 200k copper @ 600 gold
    ("sell", "bauxite", 200000, 600),  # 200k bauxite @ 1,200 gold
    # === BUY offers — bot buys surplus from players (~50% of sell price) ===
    ("buy", "coal", 500000, 100),  # buy 500k coal @ 200 gold
    ("buy", "iron", 500000, 350),  # buy 500k iron @ 700 gold
    ("buy", "lumber", 500000, 150),  # buy 500k lumber @ 300 gold
    ("buy", "oil", 500000, 300),  # buy 500k oil @ 600 gold
    ("buy", "copper", 500000, 150),  # buy 500k copper @ 300 gold
    ("buy", "bauxite", 500000, 300),  # buy 500k bauxite @ 600 gold
]



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




def refresh_bot_offers():
    """Delete old bot offers and create fresh ones for essential resources."""
    from database import get_db_connection

    with get_db_connection() as conn:
        db = conn.cursor()

        # Delete ALL existing bot offers first (cleans up stale/removed offers)
        db.execute("DELETE FROM offers WHERE user_id = %s", (BOT_USER_ID,))

        for offer_type, resource, amount, price in BOT_OFFERS:
            db.execute(
                "INSERT INTO offers (user_id, type, resource, amount, price) "
                "VALUES (%s, %s, %s, %s, %s)",
                (BOT_USER_ID, offer_type, resource, amount, price),
            )

        print(f"Bot offers refreshed: {len(BOT_OFFERS)} offers created")




def market_bot_fight_wars():
    """Market Bot (ID 9999) automatically fights anyone it's at war with."""
    from database import get_db_connection
    from attack_scripts.Nations import Military
    from units import Units
    import random
    
    with get_db_connection() as conn:
        with conn.cursor() as db:
            db.execute("SELECT id, attacker, defender, war_type FROM wars WHERE (attacker=9999 OR defender=9999) AND peace_date IS NULL")
            active_wars = db.fetchall()
            
    if not active_wars:
        return
        
    for war in active_wars:
        enemy_id = war[2] if war[1] == 9999 else war[1]
        
        # Ensure bot has massive army and supplies
        bot_military = Military.get_military(9999)
        if sum(bot_military.values()) < 100000:
            with get_db_connection() as conn:
                with conn.cursor() as db:
                    db.execute("""
                        INSERT INTO user_military (user_id, unit_id, quantity)
                        SELECT 9999, unit_id, 1000000 
                        FROM unit_dictionary WHERE is_active=TRUE
                        ON CONFLICT (user_id, unit_id) DO UPDATE SET quantity = 1000000
                    """)
                    db.execute("""
                        INSERT INTO user_economy (user_id, resource_id, quantity)
                        SELECT 9999, resource_id, 10000000
                        FROM resource_dictionary WHERE is_active=TRUE
                        ON CONFLICT (user_id, resource_id) DO UPDATE SET quantity = 10000000
                    """)
            bot_military = Military.get_military(9999)
            
        available_units = [u for u, qty in bot_military.items() if qty > 0 and u not in ['spies']]
        if not available_units:
            continue
            
        random.shuffle(available_units)
        selected_types = available_units[:3]
        
        send_units = {}
        for u in selected_types:
            send_units[u] = max(1, int(bot_military[u] * 0.15)) # Send 15% of bot's units
            
        bot_units = Units(9999, send_units, selected_units_list=selected_types)
        bot_units.selected_units = send_units
        
        from app import app  # lazy: avoid circular import at worker boot

        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess["user_id"] = 9999
                sess["username"] = "System"
                sess["enemy_id"] = enemy_id
                sess["attack_units"] = bot_units.__dict__
                
            try:
                client.get("/warResult")
                print(f"Market bot attacked user {enemy_id}")
            except Exception as e:
                print(f"Market bot failed to attack user {enemy_id}: {e}")




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


