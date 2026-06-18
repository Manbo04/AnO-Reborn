import psycopg2
import os

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    DATABASE_URL = "postgres://postgres:postgres@localhost:5432/ano_reborn"

def check_influence():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        # Check users schema
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'users'")
        columns = [row[0] for row in cur.fetchall()]
        print("Users columns:", columns)
        
        # Check stats schema
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'stats'")
        stats_columns = [row[0] for row in cur.fetchall()]
        print("Stats columns:", stats_columns)
        
        # We need to find what column stores "influence" or "score". It could be "influence" in users or stats.
        if "influence" in columns:
            cur.execute("SELECT id, username, influence FROM users ORDER BY influence DESC LIMIT 5")
            print("Top users by influence in users table:")
            for row in cur.fetchall():
                print(row)
        elif "influence" in stats_columns:
            cur.execute("SELECT users.id, users.username, stats.influence FROM users JOIN stats ON users.id = stats.id ORDER BY stats.influence DESC LIMIT 5")
            print("Top users by influence in stats table:")
            for row in cur.fetchall():
                print(row)
        else:
            print("Influence column not found. Looking for 'score'.")
            if "score" in columns:
                cur.execute("SELECT id, username, score FROM users ORDER BY score DESC LIMIT 5")
                print(cur.fetchall())
            elif "score" in stats_columns:
                cur.execute("SELECT users.id, users.username, stats.score FROM users JOIN stats ON users.id = stats.id ORDER BY stats.score DESC LIMIT 5")
                print(cur.fetchall())

    except Exception as e:
        print("Error:", e)

check_influence()
