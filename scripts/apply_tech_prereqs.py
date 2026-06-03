import psycopg2
import os

def apply_prereqs():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set")
        return

    connection = psycopg2.connect(database_url)
    db = connection.cursor()

    updates = [
        # Nuclear progression
        ("nuclear_testing_facility", "better_engineering"),
        ("ballistic_missile_silo", "nuclear_testing_facility"),
        ("icbm_silo", "ballistic_missile_silo"),
        
        # Propaganda and Looting
        ("widespread_propaganda", "government_regulation"),
        ("looting_teams", "organized_supply_lines"),
    ]

    for tech_name, prereq_name in updates:
        db.execute(
            """
            UPDATE tech_dictionary 
            SET prerequisite_tech_id = (SELECT tech_id FROM tech_dictionary WHERE name = %s)
            WHERE name = %s;
            """,
            (prereq_name, tech_name)
        )
        print(f"Set prerequisite for {tech_name} to {prereq_name}")

    connection.commit()
    db.close()
    connection.close()
    print("Done applying prerequisites!")

if __name__ == "__main__":
    apply_prereqs()
