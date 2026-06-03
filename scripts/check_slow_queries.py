import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def main():
    db_url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
    if not db_url:
        print("No DATABASE_URL found.")
        return
        
    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        
        # Check if pg_stat_statements is enabled
        try:
            cur.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements;")
            conn.commit()
        except Exception as e:
            print("Could not create pg_stat_statements:", e)
            conn.rollback()

        query = """
        SELECT query, calls, total_exec_time, mean_exec_time, rows
        FROM pg_stat_statements
        ORDER BY total_exec_time DESC
        LIMIT 15;
        """
        cur.execute(query)
        rows = cur.fetchall()
        
        print("Top 15 Slowest Queries by Total Execution Time:")
        for row in rows:
            query_text = row[0][:100].replace('\n', ' ')
            print(f"Calls: {row[1]:>5} | Mean: {row[3]:>8.2f}ms | Total: {row[2]:>8.2f}ms | Rows: {row[4]:>6} | Query: {query_text}...")
            
        cur.close()
        conn.close()
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    main()
