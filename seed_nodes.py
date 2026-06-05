import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")

def seed_nodes():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    
    print("Seeding initial nodes...")
    
    nodes_data = [
        ("Global Command Center", "fortress", 0, 0),
        ("Northern Resource Hub", "resource", 300, -200),
        ("Southern Outpost", "strategic", -150, 400),
        ("Eastern Tech Core", "resource", 500, 100),
        ("Western Relay Station", "strategic", -400, -50),
        ("Deep Space Observatory", "fortress", 200, 350),
        ("Abandoned Missile Silo", "fortress", -300, -300)
    ]
    
    for name, type_, x, y in nodes_data:
        cur.execute(
            """
            INSERT INTO nodes (name, type, coordinate_x, coordinate_y, health)
            VALUES (%s, %s, %s, %s, 1000)
            """,
            (name, type_, x, y)
        )
        
    conn.commit()
    cur.close()
    conn.close()
    print("Successfully seeded 7 nodes!")

if __name__ == "__main__":
    seed_nodes()
