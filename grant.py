import os
import psycopg2

db_url = os.environ.get("DATABASE_URL")
if not db_url:
    print("No DATABASE_URL found.")
    exit(1)

print("Connecting to", db_url)
try:
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    cursor = conn.cursor()
    
    queries = [
        "UPDATE user_economy SET quantity = quantity + 120000 WHERE user_id = 8 AND resource_id = (SELECT resource_id FROM resource_dictionary WHERE name = 'lumber');",
        "UPDATE user_economy SET quantity = quantity + 50000 WHERE user_id = 8 AND resource_id = (SELECT resource_id FROM resource_dictionary WHERE name = 'iron');",
        "UPDATE user_economy SET quantity = quantity + 50000 WHERE user_id = 8 AND resource_id = (SELECT resource_id FROM resource_dictionary WHERE name = 'coal');",
        "UPDATE user_economy SET quantity = quantity + 350000 WHERE user_id = 8 AND resource_id = (SELECT resource_id FROM resource_dictionary WHERE name = 'rations');",
        "UPDATE user_economy SET quantity = quantity + 15000 WHERE user_id = 8 AND resource_id = (SELECT resource_id FROM resource_dictionary WHERE name = 'steel');",
        "UPDATE user_economy SET quantity = quantity + 10000 WHERE user_id = 8 AND resource_id = (SELECT resource_id FROM resource_dictionary WHERE name = 'components');",
        "UPDATE user_economy SET quantity = quantity + 10000 WHERE user_id = 8 AND resource_id = (SELECT resource_id FROM resource_dictionary WHERE name = 'aluminium');"
    ]
    for q in queries:
        cursor.execute(q)
        print("Executed:", q)
    
    print("Resources granted successfully to user 8!")
except Exception as e:
    print("Error:", e)
