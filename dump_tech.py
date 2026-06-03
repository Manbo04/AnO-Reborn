import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import get_db_connection

with get_db_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT tech_id, name, display_name, research_cost, prerequisite_tech_id FROM tech_dictionary;")
    rows = cursor.fetchall()
    for row in rows:
        print(f"ID: {row[0]}, Name: {row[1]}, Cost: {row[3]}, Prereq: {row[4]}")
