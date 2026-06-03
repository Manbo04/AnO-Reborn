import os
from database import get_db_connection

def migrate_population_to_bigint():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Check current type of population
            cur.execute("""
                SELECT data_type FROM information_schema.columns 
                WHERE table_name = 'provinces' AND column_name = 'population'
            """)
            print("provinces.population type:", cur.fetchone()[0])
            
            print("Altering columns to BIGINT...")
            cur.execute("ALTER TABLE provinces ALTER COLUMN population TYPE BIGINT;")
            cur.execute("ALTER TABLE provinces ALTER COLUMN pop_children TYPE BIGINT;")
            cur.execute("ALTER TABLE provinces ALTER COLUMN pop_working TYPE BIGINT;")
            cur.execute("ALTER TABLE provinces ALTER COLUMN pop_elderly TYPE BIGINT;")
            conn.commit()
            print("Done!")

if __name__ == "__main__":
    migrate_population_to_bigint()
