import os
import psycopg2
from psycopg2.extras import RealDictCursor

def main():
    url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
    if not url:
        print("No database URL found.")
        return
    
    try:
        conn = psycopg2.connect(url)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("SELECT id, username, discord_id FROM users WHERE username ILIKE '%%dede%%' OR username ILIKE '%%manbo04%%' LIMIT 10;")
        rows = cursor.fetchall()
        
        if rows:
            for row in rows:
                print(f"User found: {row['username']} (ID: {row['id']}) - Discord ID: {row.get('discord_id', 'NULL')}")
        else:
            print("No matching users found.")
            
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Database error: {e}")

if __name__ == "__main__":
    main()
