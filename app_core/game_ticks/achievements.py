import os
from database import get_db_cursor
from psycopg2.extras import execute_batch
from app_core.game_ticks.locks import try_pg_advisory_lock

# All queries must SELECT a single column: the qualifying user_id.
# Verified against the real schema on edu DB (postgresql://postgres@localhost:55450/edu).
ACHIEVEMENT_QUERIES = [
    # Economy
    ("eco_mall_1", """
        SELECT ub.user_id
        FROM user_buildings ub
        JOIN building_dictionary bd ON ub.building_id = bd.building_id
        WHERE bd.name = 'malls'
        GROUP BY ub.user_id HAVING SUM(ub.quantity) >= 1
    """),
    ("eco_cg_all", """
        SELECT ub.user_id
        FROM user_buildings ub
        JOIN building_dictionary bd ON ub.building_id = bd.building_id
        WHERE bd.name IN ('malls', 'gas_stations', 'general_stores', 'distribution_centers', 'food_banks')
        GROUP BY ub.user_id HAVING COUNT(DISTINCT bd.name) >= 5
    """),
    ("eco_treasury_1b",  "SELECT id FROM stats WHERE gold >= 1000000000"),
    ("eco_treasury_100b", "SELECT id FROM stats WHERE gold >= 100000000000"),
    ("eco_treasury_1t",  "SELECT id FROM stats WHERE gold >= 1000000000000"),
    ("eco_bond_issued",  "SELECT DISTINCT issuer_id FROM bonds WHERE status != 'draft'"),
    ("eco_bond_funded",  "SELECT DISTINCT issuer_id FROM bonds WHERE status IN ('active', 'completed', 'defaulted')"),
    ("eco_currency_minted", "SELECT DISTINCT user_id FROM national_currency_conversions WHERE direction = 'mint'"),

    # Population — stored per-province; sum across all provinces owned by each user.
    # stats has no population column; provinces.population is per-province.
    ("pop_1m",  "SELECT userid FROM provinces GROUP BY userid HAVING SUM(population) >=       1000000"),
    ("pop_100m", "SELECT userid FROM provinces GROUP BY userid HAVING SUM(population) >=     100000000"),
    ("pop_1b",  "SELECT userid FROM provinces GROUP BY userid HAVING SUM(population) >= 1000000000"),

    # Expansion — provinces uses userid (not owner_id) and citycount (not cities).
    ("exp_prov_5",  "SELECT userid FROM provinces WHERE userid IS NOT NULL GROUP BY userid HAVING COUNT(id) >= 5"),
    ("exp_prov_20", "SELECT userid FROM provinces WHERE userid IS NOT NULL GROUP BY userid HAVING COUNT(id) >= 20"),
    ("exp_prov_50", "SELECT userid FROM provinces WHERE userid IS NOT NULL GROUP BY userid HAVING COUNT(id) >= 50"),
    ("exp_cities_1000", "SELECT userid FROM provinces WHERE userid IS NOT NULL GROUP BY userid HAVING SUM(citycount) >= 1000"),

    # Military — wars table (wars_normalized does not exist); winner_id is set on concluded wars.
    # user_military uses quantity (not amount).
    ("mil_war_won", "SELECT winner_id FROM wars WHERE winner_id IS NOT NULL GROUP BY winner_id"),
    ("mil_spy_op",  "SELECT spyer FROM spyinfo GROUP BY spyer"),
    ("mil_carrier", """
        SELECT um.user_id
        FROM user_military um
        JOIN unit_dictionary ud ON ud.unit_id = um.unit_id
        WHERE ud.name IN ('aircraft_carrier', 'aircraft_carriers')
        GROUP BY um.user_id HAVING SUM(um.quantity) >= 1
    """),

    # Diplomacy
    ("dip_coalition", "SELECT user_id FROM coalition_members"),
    ("dip_treaty", "SELECT sender_id FROM nation_treaties UNION SELECT recipient_id FROM nation_treaties"),

    # Fun
    ("fun_nuke", "SELECT attacker_id FROM nuclear_strikes"),
    ("fun_debt", "SELECT id FROM stats WHERE gold < 0"),
]


def check_achievements():
    """Evaluate all achievements via batched SQL.

    Correctness guarantees:
    - Each achievement key is wrapped in a SAVEPOINT so a bad query for one
      key cannot abort later keys in the same transaction.
    - Silent backfill is per-key: if a key has zero existing rows in
      user_achievements before this run, new unlocks are inserted without
      writing any news rows (first-time population of historical data).
      Only subsequent runs write news for genuinely new unlocks.
    - Inserts use ON CONFLICT DO NOTHING to tolerate concurrent writers.
    - The advisory lock is transaction-scoped (pg_try_advisory_xact_lock)
      and is released automatically on COMMIT/ROLLBACK at the end of the
      get_db_cursor context.
    """
    with get_db_cursor() as db:
        # Transaction-scoped advisory lock — released automatically on commit.
        # get_db_cursor yields a cursor; .connection is the underlying psycopg2 conn.
        if not try_pg_advisory_lock(db.connection, 10095, "achievements"):
            return

        # Pre-fetch achievement names for news messages.
        db.execute("SELECT key, name FROM achievements")
        achievement_names = {row[0]: row[1] for row in db.fetchall()}

        total_new_unlocks = 0

        for key, query in ACHIEVEMENT_QUERIES:
            sp = f"sp_ach_{key}"
            db.execute(f"SAVEPOINT {sp}")
            try:
                db.execute(query)
                eligible_users = set(row[0] for row in db.fetchall() if row[0] is not None)

                if not eligible_users:
                    db.execute(f"RELEASE SAVEPOINT {sp}")
                    continue

                # Per-key backfill detection: does this key already have ANY rows?
                db.execute(
                    "SELECT user_id FROM user_achievements WHERE key = %s",
                    (key,),
                )
                existing_users = set(row[0] for row in db.fetchall())
                key_is_first_run = (len(existing_users) == 0)

                new_users = eligible_users - existing_users
                if not new_users:
                    db.execute(f"RELEASE SAVEPOINT {sp}")
                    continue

                total_new_unlocks += len(new_users)

                # Insert new unlocks — ON CONFLICT DO NOTHING guards against races.
                insert_args = [(uid, key) for uid in new_users]
                execute_batch(
                    db,
                    "INSERT INTO user_achievements (user_id, key) VALUES (%s, %s)"
                    " ON CONFLICT DO NOTHING",
                    insert_args,
                    page_size=100,
                )

                # Write news only when this key already had existing rows before
                # this run (i.e. not a fresh backfill of historical data).
                if not key_is_first_run:
                    ach_name = achievement_names.get(key, "Unknown Achievement")
                    news_msg = f"Achievement Unlocked: {ach_name}!"
                    news_args = [(uid, news_msg) for uid in new_users]
                    execute_batch(
                        db,
                        "INSERT INTO news (destination_id, message) VALUES (%s, %s)",
                        news_args,
                        page_size=100,
                    )

                db.execute(f"RELEASE SAVEPOINT {sp}")

            except Exception as e:
                print(f"[achievements] Error checking {key}: {e}")
                db.execute(f"ROLLBACK TO SAVEPOINT {sp}")
                try:
                    db.execute(f"RELEASE SAVEPOINT {sp}")
                except Exception:
                    pass

        if total_new_unlocks > 0:
            print(f"[achievements] Unlocked {total_new_unlocks} total achievements across all players.")
