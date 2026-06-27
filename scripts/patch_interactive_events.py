import os
import psycopg2
from urllib.parse import urlparse
from dotenv import load_dotenv

def migrate():
    print("Connecting to local database...")
    
    load_dotenv("/Users/dede/AnO-Reborn/.env")
    db_url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
    if db_url:
        parsed = urlparse(db_url)
        os.environ["PG_HOST"] = parsed.hostname or "localhost"
        os.environ["PG_PORT"] = str(parsed.port or "5432")
        os.environ["PG_USER"] = parsed.username or "postgres"
        os.environ["PG_PASSWORD"] = parsed.password or ""
        os.environ["PG_DATABASE"] = parsed.path[1:] if parsed.path else "postgres"
        
    try:
        conn = psycopg2.connect(
            host=os.environ.get("LOCAL_PG_HOST") or os.environ.get("PG_HOST", "localhost"),
            port=os.environ.get("LOCAL_PG_PORT") or os.environ.get("PG_PORT", "5432"),
            user=os.environ.get("LOCAL_PG_USER") or os.environ.get("PG_USER", "dede"),
            password=os.environ.get("LOCAL_PG_PASSWORD") or os.environ.get("PG_PASSWORD", ""),
            dbname=os.environ.get("LOCAL_PG_DATABASE") or os.environ.get("PG_DATABASE", "ano"),
            sslmode="require" if "interchange" in (os.environ.get("LOCAL_PG_HOST") or os.environ.get("PG_HOST", "")) else "prefer"
        )
        conn.autocommit = True
        cur = conn.cursor()
        
        create_table_query = """
        CREATE TABLE IF NOT EXISTS interactive_events (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            event_def_id VARCHAR,
            created_at TIMESTAMP DEFAULT now(),
            resolved_at TIMESTAMP,
            chosen_option_index INTEGER,
            province_id INTEGER
        );
        """
        cur.execute(create_table_query)
        print("Successfully created table 'interactive_events' (or it already existed).")
        
        cur.close()
        conn.close()
    except Exception as e:
        print(f"An error occurred during migration: {e}")

if __name__ == "__main__":
    migrate()
