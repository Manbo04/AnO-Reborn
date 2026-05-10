import psycopg2
import os
import config

def migrate():
    try:
        conn = psycopg2.connect(config.get_database_url())
        cur = conn.cursor()
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS recovery_key VARCHAR(255)")
        # Also add discord_id for Discord account linking
        print("Ensuring discord_id column exists...")
        cur.execute("""
            ALTER TABLE users 
            ADD COLUMN IF NOT EXISTS discord_id VARCHAR(255)
        """)
        print("discord_id column verified.")

        conn.commit()
        print("Successfully added recovery_key column to users table.")
    except Exception as e:
        print(f"Migration failed: {e}")
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    migrate()
