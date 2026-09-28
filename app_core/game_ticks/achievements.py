import os
from database import get_db_cursor
from psycopg2.extras import execute_batch
from app_core.game_ticks.locks import try_pg_advisory_lock

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
    ("eco_treasury_1b", "SELECT id FROM stats WHERE gold >= 1000000000"),
    ("eco_treasury_100b", "SELECT id FROM stats WHERE gold >= 100000000000"),
    ("eco_treasury_1t", "SELECT id FROM stats WHERE gold >= 1000000000000"),
    ("eco_bond_issued", "SELECT DISTINCT issuer_id FROM bonds WHERE status != 'draft'"),
    ("eco_bond_funded", "SELECT DISTINCT issuer_id FROM bonds WHERE status IN ('active', 'completed', 'defaulted')"),
    ("eco_currency_minted", "SELECT DISTINCT user_id FROM national_currency_conversions WHERE direction = 'mint'"),
    
    # Population
    ("pop_1m", "SELECT id FROM stats WHERE population >= 1000000"),
    ("pop_100m", "SELECT id FROM stats WHERE population >= 100000000"),
    ("pop_1b", "SELECT id FROM stats WHERE population >= 1000000000"),

    # Expansion
    ("exp_prov_5", "SELECT owner_id FROM provinces WHERE owner_id IS NOT NULL GROUP BY owner_id HAVING COUNT(id) >= 5"),
    ("exp_prov_20", "SELECT owner_id FROM provinces WHERE owner_id IS NOT NULL GROUP BY owner_id HAVING COUNT(id) >= 20"),
    ("exp_prov_50", "SELECT owner_id FROM provinces WHERE owner_id IS NOT NULL GROUP BY owner_id HAVING COUNT(id) >= 50"),
    ("exp_cities_1000", "SELECT owner_id FROM provinces WHERE owner_id IS NOT NULL GROUP BY owner_id HAVING SUM(cities) >= 1000"),

    # Military
    ("mil_war_won", "SELECT winner_id FROM wars_normalized WHERE winner_id IS NOT NULL GROUP BY winner_id"),
    ("mil_spy_op", "SELECT spyer FROM spyinfo GROUP BY spyer"),
    ("mil_carrier", """
        SELECT um.user_id
        FROM user_military um
        JOIN unit_dictionary ud ON ud.unit_id = um.unit_id
        WHERE ud.name = 'aircraft_carrier'
        GROUP BY um.user_id HAVING SUM(um.amount) >= 1
    """),

    # Diplomacy
    ("dip_coalition", "SELECT user_id FROM coalition_members"),
    ("dip_treaty", "SELECT sender_id FROM nation_treaties UNION SELECT recipient_id FROM nation_treaties"),

    # Fun
    ("fun_nuke", "SELECT attacker_id FROM nuclear_strikes"),
    ("fun_debt", "SELECT id FROM stats WHERE gold < 0")
]

def check_achievements():
    """Evaluate all achievements via batched SQL."""
    with get_db_cursor() as db:
        if not try_pg_advisory_lock(db.connection, 10095, "achievements"):
            return

        db.execute("SELECT COUNT(*) FROM user_achievements")
        total_unlocked = db.fetchone()[0]
        is_first_run = (total_unlocked == 0)

        # Pre-fetch achievement names for news messages
        db.execute("SELECT key, name FROM achievements")
        achievement_names = {row[0]: row[1] for row in db.fetchall()}

        total_new_unlocks = 0

        for key, query in ACHIEVEMENT_QUERIES:
            try:
                db.execute(query)
                eligible_users = set(row[0] for row in db.fetchall() if row[0] is not None)
                
                if not eligible_users:
                    continue

                db.execute("SELECT user_id FROM user_achievements WHERE key = %s", (key,))
                existing_users = set(row[0] for row in db.fetchall())

                new_users = eligible_users - existing_users
                if not new_users:
                    continue

                total_new_unlocks += len(new_users)

                # Insert new unlocks
                insert_args = [(uid, key) for uid in new_users]
                execute_batch(
                    db,
                    "INSERT INTO user_achievements (user_id, key) VALUES (%s, %s)",
                    insert_args,
                    page_size=100
                )

                # Send news notifications if it's not the first backfill run
                if not is_first_run:
                    ach_name = achievement_names.get(key, "Unknown Achievement")
                    news_msg = f"Achievement Unlocked: {ach_name}!"
                    news_args = [(uid, news_msg) for uid in new_users]
                    execute_batch(
                        db,
                        "INSERT INTO news (destination_id, message) VALUES (%s, %s)",
                        news_args,
                        page_size=100
                    )

            except Exception as e:
                print(f"[achievements] Error checking {key}: {e}")

        if total_new_unlocks > 0:
            print(f"[achievements] Unlocked {total_new_unlocks} total achievements across all players.")
